"""Embedding functions by arm name. Ported from pixels-rag core/embeddings.py
and core/index.py (the hash test embedder); see docs/PROVENANCE.md. The
ablation runner that used to live beside this moves to Part 6.

The default stays local. all-MiniLM-L6-v2 reads at most 256 wordpieces, so a
400-token chunk is embedded from its first ~240 tokens; bge-small and
e5-small read 512. The ingest report counts the chunks over the limit."""

from pathlib import Path

from chromadb.api.types import EmbeddingFunction

ARMS = {
    "minilm": {"model": "all-MiniLM-L6-v2", "max_wordpieces": 256, "needs": "nothing (Chroma's default ONNX model, downloaded once)"},
    "bge-small": {"model": "BAAI/bge-small-en-v1.5", "max_wordpieces": 512, "needs": "pip install sentence-transformers, and the model download"},
    "e5-small": {"model": "intfloat/e5-small-v2", "max_wordpieces": 512, "needs": "pip install sentence-transformers, and the model download"},
    "hash": {"model": "hash-test", "max_wordpieces": None, "needs": "nothing; the offline test embedder, not a contender"},
}
DEFAULT = "minilm"


class HashEmbedding(EmbeddingFunction):
    """A bag-of-words hash embedding: deterministic, offline. For tests only."""

    DIMS = 1024

    def __init__(self):
        pass

    def __call__(self, input):
        out = []
        for text in input:
            vec = [0.0] * self.DIMS
            for tok in str(text).lower().replace(",", " ").replace(":", " ").split():
                h = 0
                for ch in tok:
                    h = (h * 31 + ord(ch)) & 0xFFFFFFFF
                vec[h % self.DIMS] += 1.0
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out

    @staticmethod
    def name():
        return "hash-test"

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config):
        return HashEmbedding()

    @staticmethod
    def validate_config(config):
        return None

    @staticmethod
    def validate_config_update(old_config, new_config):
        return None


def make_embedding_function(name: str):
    """(embedding_function, model label). None means Chroma's default."""
    if name not in ARMS:
        raise ValueError(f"unknown embedding arm {name!r}; choose from {', '.join(ARMS)}")
    arm = ARMS[name]
    if name == "hash":
        return HashEmbedding(), arm["model"]
    if name == "minilm":
        return None, arm["model"]
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        return SentenceTransformerEmbeddingFunction(model_name=arm["model"]), arm["model"]
    except Exception as e:
        raise RuntimeError(f"{name} needs {arm['needs']} ({type(e).__name__}: {str(e)[:80]})") from e


MINILM_TOKENIZER = Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2" / "onnx" / "tokenizer.json"


def wordpiece_counter(path: Path = MINILM_TOKENIZER):
    """A function text list -> wordpiece counts (without [CLS]/[SEP]) from
    the MiniLM tokenizer Chroma downloads, or None when it is not on disk."""
    if not Path(path).exists():
        return None
    try:
        from tokenizers import Tokenizer
    except ImportError:
        return None
    tok = Tokenizer.from_file(str(path))
    tok.no_truncation()
    return lambda texts: [len(e.ids) - 2 for e in tok.encode_batch(list(texts))]
