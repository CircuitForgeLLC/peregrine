"""
Vision service — moondream2 inference for survey screenshot analysis.

Start: bash scripts/manage-vision.sh start
Or directly: conda run -n job-seeker-vision uvicorn scripts.vision_service.main:app --port 8002

First run downloads moondream2 from HuggingFace (~1.8GB).
Model is loaded lazily on first /analyze request and stays resident.
GPU is used if available (CUDA); falls back to CPU.
4-bit quantization on GPU keeps VRAM footprint ~1.5GB.
"""
import base64
import io

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Job Seeker Vision Service")

# Module-level model state — lazy loaded on first /analyze request
_model = None
_tokenizer = None
_device = "cpu"
_loading = False


def _load_model() -> None:
    global _model, _tokenizer, _device, _loading
    if _model is not None:
        return
    _loading = True
    print("[vision] Loading moondream2…")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_id = "vikhyatk/moondream2"
    revision = "2025-01-09"
    _device = "cuda" if torch.cuda.is_available() else "cpu"

    if _device == "cuda":
        from transformers import BitsAndBytesConfig
        bnb = BitsAndBytesConfig(load_in_4bit=True)
        _model = AutoModelForCausalLM.from_pretrained(
            model_id, revision=revision,
            quantization_config=bnb,
            trust_remote_code=True,
            device_map="auto",
        )
    else:
        _model = AutoModelForCausalLM.from_pretrained(
            model_id, revision=revision,
            trust_remote_code=True,
        )
        _model.to(_device)

    _tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
    _loading = False
    print(f"[vision] moondream2 ready on {_device}")


class AnalyzeRequest(BaseModel):
    prompt: str
    image_base64: str


class AnalyzeResponse(BaseModel):
    text: str


@app.get("/health")
def health():
    import torch
    return {
        "status": "loading" if _loading else "ok",
        "model": "moondream2",
        "gpu": torch.cuda.is_available(),
        "loaded": _model is not None,
    }


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    from PIL import Image
    import torch

    _load_model()

    try:
        image_data = base64.b64decode(req.image_base64)
        image = Image.open(io.BytesIO(image_data)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")

    with torch.no_grad():
        enc_image = _model.encode_image(image)
        answer = _model.answer_question(enc_image, req.prompt, _tokenizer)

    return AnalyzeResponse(text=answer)
