"""Generate local EmbeddingGemma 2 vectors before the Lab 9 index exercise.

Run --mode text for token lengths, truncation, and overlapping chunks.
Run --mode media with local --image, --audio, and --video files.
These demonstrations do not change the supplied arXiv vectors.
"""

import argparse
from pathlib import Path

MODEL_ID = "google/embeddinggemma-2"
CONTEXT_TOKENS = 8192
PARAGRAPH = (
    "A transaction log records changes before data pages reach storage. "
    "After a crash, recovery uses the log to restore committed updates. "
    "A checkpoint reduces the amount of log that recovery must inspect. "
    "The recovery procedure must preserve the database's consistency. "
)
TAIL = "The backup cabinet access code is AMBER-OTTER-731."


def load_model(mode, device):
    import torch
    from sentence_transformers import SentenceTransformer

    config = {"vision_config": None, "audio_config": None} if mode == "text" else {}
    model = SentenceTransformer(
        MODEL_ID, device=device, config_kwargs=config,
        model_kwargs={"torch_dtype": torch.float32},
    )
    # The architecture's position limit can exceed the supported embedding window.
    model.max_seq_length = CONTEXT_TOKENS
    model.tokenizer.truncation_side = "right"
    return model


def text_token_ids(model, text, prompt_name="Document", truncate=False):
    """Use the encode preprocessing path, including prompts and special tokens."""
    kwargs = {} if truncate else {"processing_kwargs": {"text": {"truncation": False}}}
    features = model.preprocess([text], prompt=model.prompts[prompt_name], **kwargs)
    return features["input_ids"][0].tolist()


def check_text_length(model, text, prompt_name="Document"):
    count = len(text_token_ids(model, text, prompt_name))
    if count > model.max_seq_length:
        raise ValueError(f"{count} formatted tokens exceed the {model.max_seq_length}-token window")
    return count


def chunk_text(model, text, max_tokens=512, overlap=64):
    """Keep raw token offsets and recheck each complete, prompted chunk."""
    limit = min(max_tokens, model.max_seq_length)
    overhead = len(text_token_ids(model, ""))
    budget = limit - overhead
    if not 0 <= overlap < budget:
        raise ValueError("The overlap must fit inside the chunk's content budget")
    ids = model.tokenizer.encode(text, add_special_tokens=False)
    chunks, start = [], 0
    while start < len(ids):
        end = min(start + budget, len(ids))
        candidate = model.tokenizer.decode(ids[start:end], skip_special_tokens=True)
        # Decoding and re-encoding can change token boundaries. Check, then shrink.
        while len(text_token_ids(model, candidate)) > limit:
            end -= 1
            if end <= start:
                raise ValueError("One content token cannot fit with the document prompt")
            candidate = model.tokenizer.decode(ids[start:end], skip_special_tokens=True)
        chunks.append({"start": start, "end": end, "text": candidate})
        if end == len(ids):
            break
        if end - start <= overlap:
            raise ValueError("Reduce the overlap to allow this chunk to advance")
        start = end - overlap
    return chunks


def encode_text(model, texts, prompt_name="Document"):
    for text in texts:
        check_text_length(model, text, prompt_name)
    return model.encode(texts, prompt_name=prompt_name, batch_size=1,
                        normalize_embeddings=True, show_progress_bar=True)


def show_vector(label, vector):
    import numpy as np

    if vector.shape != (768,) or not np.isfinite(vector).all():
        raise ValueError(f"{label}: expected a finite 768-dimensional vector")
    print(f"{label}: shape={vector.shape}, norm={np.linalg.norm(vector):.6f}")
    print("  first six coordinates:", np.round(vector[:6], 5))


def run_text(model):
    examples = {
        "short": "A transaction log helps a database recover after a crash.",
        "medium": PARAGRAPH * 3,
        "long": PARAGRAPH * 32,
    }
    print(f"Model: {MODEL_ID}; input window: {model.max_seq_length} tokens")
    for name, text in examples.items():
        print(f"{name}: {len(text)} characters, {check_text_length(model, text)} formatted tokens")
    vectors = encode_text(model, list(examples.values()))
    for name, vector in zip(examples, vectors):
        show_vector(name, vector)

    # Place the useful fact beyond the input window, not merely at a word limit.
    prefix = PARAGRAPH
    while len(text_token_ids(model, prefix)) <= model.max_seq_length + 128:
        prefix *= 2
    oversized = prefix + TAIL
    try:
        check_text_length(model, oversized)
    except ValueError as error:
        print("\nStrict application check:", error)
    retained = text_token_ids(model, oversized, truncate=True)
    other_tail = text_token_ids(model, prefix + "The cabinet code is BLUE-FOX-942.", truncate=True)
    print(f"Right-truncating preprocessing retains {len(retained)} tokens.")
    print(f"Different discarded endings produce identical token IDs: {retained == other_tail}")
    if len(retained) > model.max_seq_length or retained != other_tail:
        raise RuntimeError("Preprocessing behavior changed. Inspect truncation before encoding.")
    print("The model receives the same input for both endings, so it cannot distinguish them.")

    chunks = chunk_text(model, oversized)
    print(f"\nSplit the same text into {len(chunks)} chunks, with up to 512 formatted tokens and 64-token overlap.")
    print(f"Tail fact survives in a chunk: {any(TAIL in chunk['text'] for chunk in chunks)}")
    chunk_vectors = encode_text(model, [chunk["text"] for chunk in chunks])
    query = "What is the backup cabinet access code?"
    query_vector = encode_text(model, [query], "SearchQuery")[0]
    scores = chunk_vectors @ query_vector  # Dot product equals cosine for unit vectors.
    print(f"Query: {query}")
    ranking = sorted(range(len(chunks)), key=lambda i: (-float(scores[i]), i))
    for i in ranking[:3]:
        chunk = chunks[i]
        print(f"  handbook/chunk-{i}: tokens [{chunk['start']}, {chunk['end']}), cosine={scores[i]:.4f}")
        print("   ", chunk["text"][-180:])
    for i, chunk in enumerate(chunks):
        if TAIL in chunk["text"]:
            print(f"Tail fact: handbook/chunk-{i}, rank={ranking.index(i) + 1}/{len(chunks)}, cosine={scores[i]:.4f}")
            print("   ", chunk["text"][-180:])
    print("Read the returned chunks. A high similarity score does not prove that a chunk answers the question.")


def validate_media(args):
    files = []
    for kind in ("image", "audio", "video"):
        value = getattr(args, kind, None)
        if not value or not Path(value).is_file():
            raise ValueError(f"--{kind} must name an existing local file")
        files.append((kind, str(Path(value).resolve())))
    return files


def encode_media(model, kind, path):
    # Decode the short fixture with PyAV, which is included in the requirements.
    # Preserve frame timing so the model's processor can sample the video.
    if kind == "video":
        from transformers.video_utils import load_video

        frames, metadata = load_video(path, backend="pyav")
        return model.encode(
            {"video": frames}, normalize_embeddings=True,
            processing_kwargs={"video": {"video_metadata": [metadata]}},
        )
    return model.encode({kind: path}, normalize_embeddings=True)


def run_media(model, args, files):
    import numpy as np

    labels = ["text caption"] + [f"{kind}: {Path(path).name}" for kind, path in files]
    vectors = [encode_text(model, [args.caption])[0]]
    for kind, path in files:
        # Media-only inputs use no text task prefix.
        vectors.append(encode_media(model, kind, path))
    for label, vector in zip(labels, vectors):
        show_vector(label, vector)
    query_vector = encode_text(model, [args.query], "SearchQuery")[0]
    scores = np.stack(vectors) @ query_vector
    print(f"\nQuery: {args.query}")
    for i in sorted(range(len(labels)), key=lambda i: (-float(scores[i]), i)):
        print(f"  cosine={scores[i]:.4f}  {labels[i]}")
    print("Inspect the files and ranking. These toy inputs test the pipeline, not retrieval quality.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("text", "media"), default="text")
    parser.add_argument("--device", default="cpu", help="PyTorch device; CPU uses float32")
    for kind in ("image", "audio", "video"):
        parser.add_argument(f"--{kind}", help=f"local {kind} file for media mode")
    parser.add_argument("--caption", default="A red circle on a white background.")
    parser.add_argument("--query", default="a red circle moving across a white background")
    args = parser.parse_args()
    try:
        files = validate_media(args) if args.mode == "media" else []
    except ValueError as error:
        parser.error(str(error))
    model = load_model(args.mode, args.device)
    if args.mode == "text":
        run_text(model)
    else:
        run_media(model, args, files)


if __name__ == "__main__":
    main()
