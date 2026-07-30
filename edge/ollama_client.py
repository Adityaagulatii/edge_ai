import time
import requests


def query_ollama(prompt, model, ollama_url, timeout=30):
    """
    POST to {ollama_url}/api/generate with stream=False.

    Returns:
        {
            "text":        str,    # model response (empty on failure)
            "elapsed_sec": float,
            "ok":          bool,
            "error":       str,    # "" on success
        }
    """
    t0 = time.monotonic()
    try:
        resp = requests.post(
            f"{ollama_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")
        return {"text": text, "elapsed_sec": round(time.monotonic() - t0, 2), "ok": True, "error": ""}
    except requests.exceptions.Timeout:
        return {"text": "", "elapsed_sec": round(time.monotonic() - t0, 2), "ok": False, "error": "timeout"}
    except Exception as e:
        return {"text": "", "elapsed_sec": round(time.monotonic() - t0, 2), "ok": False, "error": str(e)}
