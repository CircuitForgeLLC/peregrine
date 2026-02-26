#!/usr/bin/env python3
# scripts/finetune_local.py
"""
Local LoRA fine-tune on the candidate's cover letter corpus.
No HuggingFace account or internet required after the base model is cached.

Usage:
    conda run -n ogma python scripts/finetune_local.py
    conda run -n ogma python scripts/finetune_local.py --model unsloth/Llama-3.2-3B-Instruct
    conda run -n ogma python scripts/finetune_local.py --epochs 15 --rank 16

After training, follow the printed instructions to load the model into Ollama.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Limit CUDA to GPU 0. device_map={"":0} in FastLanguageModel.from_pretrained
# pins every layer to GPU 0, avoiding the accelerate None-device bug that
# occurs with device_map="auto" on multi-GPU machines with 4-bit quantisation.
# Do NOT set WORLD_SIZE/RANK — that triggers torch.distributed initialisation.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

from scripts.user_profile import UserProfile
_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_MODEL   = "unsloth/Llama-3.2-3B-Instruct"   # safe on 8 GB VRAM

# DOCS_DIR env var overrides user_profile when running inside Docker
_docs_env = os.environ.get("DOCS_DIR", "")
_docs = Path(_docs_env) if _docs_env else (
    _profile.docs_dir if _profile else Path.home() / "Documents" / "JobSearch"
)

LETTERS_JSONL   = _docs / "training_data" / "cover_letters.jsonl"
OUTPUT_DIR      = _docs / "training_data" / "finetune_output"
GGUF_DIR        = _docs / "training_data" / "gguf"
OLLAMA_NAME     = f"{(_profile.name.split() or ['cover'])[0].lower()}-cover-writer" if _profile else "cover-writer"

SYSTEM_PROMPT = (
    f"You are {_profile.name}'s personal cover letter writer. "
    f"{_profile.career_summary}"
    if _profile else
    "You are a professional cover letter writer. Write in first person."
)

# ── Args ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--model",  default=DEFAULT_MODEL, help="Base model (HF repo id or local path)")
parser.add_argument("--epochs", type=int, default=10,  help="Training epochs (default: 10)")
parser.add_argument("--rank",   type=int, default=16,  help="LoRA rank (default: 16)")
parser.add_argument("--batch",  type=int, default=2,   help="Per-device batch size (default: 2)")
parser.add_argument("--no-gguf", action="store_true",  help="Skip GGUF export")
parser.add_argument("--max-length", type=int, default=1024, help="Max token length (default: 1024)")
args = parser.parse_args()

print(f"\n{'='*60}")
print(f"  Cover Letter Fine-Tuner  [{OLLAMA_NAME}]")
print(f"  Base model : {args.model}")
print(f"  Epochs     : {args.epochs}")
print(f"  LoRA rank  : {args.rank}")
print(f"  Dataset    : {LETTERS_JSONL}")
print(f"{'='*60}\n")

# ── Load dataset ──────────────────────────────────────────────────────────────
if not LETTERS_JSONL.exists():
    sys.exit(f"ERROR: Dataset not found at {LETTERS_JSONL}\n"
             "Run: make prepare-training  (or: python scripts/prepare_training_data.py)")

records = [json.loads(l) for l in LETTERS_JSONL.read_text().splitlines() if l.strip()]
print(f"Loaded {len(records)} training examples.")

# Convert to chat format expected by SFTTrainer
def to_messages(rec: dict) -> dict:
    return {"messages": [
        {"role": "system",    "content": SYSTEM_PROMPT},
        {"role": "user",      "content": rec["instruction"]},
        {"role": "assistant", "content": rec["output"]},
    ]}

chat_data = [to_messages(r) for r in records]

# ── Load model with unsloth ────────────────────────────────────────────────────
try:
    from unsloth import FastLanguageModel
    USE_UNSLOTH = True
except ImportError:
    USE_UNSLOTH = False
    print("WARNING: unsloth not found — falling back to standard transformers + PEFT")
    print("  Install: pip install 'unsloth[cu121-torch230] @ git+https://github.com/unslothai/unsloth.git'")

import torch

if USE_UNSLOTH:
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name   = args.model,
        max_seq_length = args.max_length,
        load_in_4bit = True,          # QLoRA — fits 7-9B in 8 GB VRAM
        dtype        = None,          # auto-detect
        device_map   = {"": 0},       # pin everything to GPU 0; avoids accelerate None-device bug
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r              = args.rank,
        lora_alpha     = args.rank * 2,
        lora_dropout   = 0,      # 0 = full unsloth kernel patching (faster)
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                          "gate_proj", "up_proj", "down_proj"],
        bias           = "none",
        use_gradient_checkpointing = "unsloth",
    )
else:
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, TaskType

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=bnb_config,
        device_map="auto",
    )
    lora_config = LoraConfig(
        r=args.rank,
        lora_alpha=args.rank * 2,
        lora_dropout=0.05,
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

# ── Build HF Dataset ──────────────────────────────────────────────────────────
from datasets import Dataset

raw = Dataset.from_list(chat_data)
split = raw.train_test_split(test_size=0.1, seed=42)
train_ds = split["train"]
eval_ds  = split["test"]
print(f"Train: {len(train_ds)}  Eval: {len(eval_ds)}")

# formatting_func must ALWAYS return a list of strings.
# Unsloth tests it with a single example dict; during training it gets batches.
# Gemma 2 has no "system" role — fold it into the first user turn.
def _apply_template(msgs):
    msgs = list(msgs)
    if msgs and msgs[0]["role"] == "system":
        sys_text = msgs.pop(0)["content"]
        if msgs and msgs[0]["role"] == "user":
            msgs[0] = {"role": "user", "content": f"{sys_text}\n\n{msgs[0]['content']}"}
    return tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)

def formatting_func(example):
    msgs_field = example["messages"]
    # Single example: messages is a list of role dicts {"role":..., "content":...}
    # Batched example: messages is a list of those lists
    if msgs_field and isinstance(msgs_field[0], dict):
        return [_apply_template(msgs_field)]
    return [_apply_template(m) for m in msgs_field]

# ── Train ─────────────────────────────────────────────────────────────────────
from trl import SFTTrainer, SFTConfig

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=train_ds,
    eval_dataset=eval_ds,
    formatting_func=formatting_func,
    args=SFTConfig(
        output_dir                  = str(OUTPUT_DIR),
        num_train_epochs            = args.epochs,
        per_device_train_batch_size = args.batch,
        gradient_accumulation_steps = max(1, 8 // args.batch),
        learning_rate               = 2e-4,
        warmup_ratio                = 0.1,
        lr_scheduler_type           = "cosine",
        fp16                        = not torch.cuda.is_bf16_supported(),
        bf16                        = torch.cuda.is_bf16_supported(),
        logging_steps               = 5,
        eval_strategy               = "epoch",
        save_strategy               = "epoch",
        load_best_model_at_end      = True,
        max_length                  = args.max_length,
        report_to                   = "none",
        push_to_hub                 = False,        # local only
    ),
)

print("\nStarting training…")
trainer.train()
print("Training complete.")

# ── Save adapter ──────────────────────────────────────────────────────────────
adapter_path = OUTPUT_DIR / "adapter"
model.save_pretrained(str(adapter_path))
tokenizer.save_pretrained(str(adapter_path))
print(f"\nLoRA adapter saved to: {adapter_path}")

# ── GGUF export ───────────────────────────────────────────────────────────────
if not args.no_gguf and USE_UNSLOTH:
    GGUF_DIR.mkdir(parents=True, exist_ok=True)
    gguf_path = GGUF_DIR / f"{OLLAMA_NAME}.gguf"
    print(f"\nExporting GGUF → {gguf_path} …")
    model.save_pretrained_gguf(
        str(GGUF_DIR / OLLAMA_NAME),
        tokenizer,
        quantization_method="q4_k_m",
    )
    # unsloth names the file automatically — find it
    gguf_files = list(GGUF_DIR.glob("*.gguf"))
    if gguf_files:
        gguf_path = gguf_files[0]
        print(f"GGUF written: {gguf_path}")
    else:
        print("GGUF export may have succeeded — check GGUF_DIR above.")
else:
    gguf_path = None

# ── Register with Ollama (auto) ────────────────────────────────────────────────

def _auto_register_ollama(gguf_path: Path, model_name: str, system_prompt: str) -> bool:
    """
    Copy GGUF into the shared Ollama models volume and register via the API.

    Works in two modes:
      Containerised — OLLAMA_MODELS_MOUNT + OLLAMA_MODELS_OLLAMA_PATH env vars
                      translate the container path into Ollama's view of the file.
      Local         — gguf_path is an absolute path Ollama can read directly.
    """
    import shutil
    import requests

    ollama_url        = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    models_mount      = os.environ.get("OLLAMA_MODELS_MOUNT", "")
    ollama_models_dir = os.environ.get("OLLAMA_MODELS_OLLAMA_PATH", "")

    # ── Place GGUF where Ollama can read it ───────────────────────────────────
    if models_mount and ollama_models_dir:
        # Containerised: write into the shared volume; Ollama reads from its own mount.
        dest_dir = Path(models_mount) / "custom"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / gguf_path.name
        if dest != gguf_path:
            print(f"Copying GGUF → shared volume: {dest}")
            shutil.copy2(gguf_path, dest)
        ollama_gguf = f"{ollama_models_dir}/custom/{gguf_path.name}"
    else:
        # Local: pass the absolute path directly.
        ollama_gguf = str(gguf_path.resolve())

    modelfile_text = (
        f"FROM {ollama_gguf}\n"
        f"SYSTEM \"\"\"\n{system_prompt}\n\"\"\"\n"
        f"PARAMETER temperature 0.7\n"
        f"PARAMETER top_p 0.9\n"
        f"PARAMETER num_ctx 32768\n"
    )

    # Write Modelfile to disk as a reference (useful for debugging)
    (OUTPUT_DIR / "Modelfile").write_text(modelfile_text)

    # ── Create via Ollama API ─────────────────────────────────────────────────
    print(f"\nRegistering '{model_name}' with Ollama at {ollama_url} …")
    try:
        r = requests.post(
            f"{ollama_url}/api/create",
            json={"name": model_name, "modelfile": modelfile_text},
            timeout=300,
            stream=True,
        )
        for line in r.iter_lines():
            if line:
                import json as _json
                try:
                    msg = _json.loads(line).get("status", "")
                except Exception:
                    msg = line.decode()
                if msg:
                    print(f"  {msg}")
        if r.status_code != 200:
            print(f"  WARNING: Ollama returned HTTP {r.status_code}")
            return False
    except Exception as exc:
        print(f"  Ollama registration failed: {exc}")
        print(f"  Run manually: ollama create {model_name} -f {OUTPUT_DIR / 'Modelfile'}")
        return False

    # ── Update config/llm.yaml ────────────────────────────────────────────────
    llm_yaml = Path(__file__).parent.parent / "config" / "llm.yaml"
    if llm_yaml.exists():
        try:
            import yaml as _yaml
            cfg = _yaml.safe_load(llm_yaml.read_text()) or {}
            if "backends" in cfg and "ollama" in cfg["backends"]:
                cfg["backends"]["ollama"]["model"] = f"{model_name}:latest"
                llm_yaml.write_text(
                    _yaml.dump(cfg, default_flow_style=False, allow_unicode=True)
                )
                print(f"  llm.yaml updated → ollama.model = {model_name}:latest")
        except Exception as exc:
            print(f"  Could not update llm.yaml automatically: {exc}")

    print(f"\n{'='*60}")
    print(f"  Model ready: {model_name}:latest")
    print(f"  Test: ollama run {model_name} 'Write a cover letter for a Senior Engineer role at Acme Corp.'")
    print(f"{'='*60}\n")
    return True


if gguf_path and gguf_path.exists():
    _auto_register_ollama(gguf_path, OLLAMA_NAME, SYSTEM_PROMPT)
else:
    print(f"\n{'='*60}")
    print("  Adapter saved (no GGUF produced).")
    print(f"  Re-run without --no-gguf to generate a GGUF for Ollama registration.")
    print(f"  Adapter path: {adapter_path}")
    print(f"{'='*60}\n")
