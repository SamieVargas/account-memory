"""Embedding functions by arm name. Ported from pixels-rag core/embeddings.py
and core/index.py (the hash test embedder); see docs/PROVENANCE.md. The
ablation runner is evals/ablation.py.

The default is all-MiniLM-L6-v2 (Samie's call, 2026-09-23), with the
brief's chunk sizes. It reads at most 256 wordpieces, so a 400-token chunk
is embedded from its first ~240 tokens; bge-small and e5-small read 512.
Every dense result reports the share of indexed chunks over the model's
limit beside it.

bge and e5 are trained with instructions: bge prefixes short queries with
a retrieval instruction, e5 prefixes "query: " and "passage: ". Chroma
embeds queries through `embed_query` when the function has one, so the
prefixes are applied on each side; without them the arms would be measured
as they are not meant to be used."""

from pathlib import Path

from chromadb.api.types import EmbeddingFunction

ARMS = {
    "minilm": {"model": "all-MiniLM-L6-v2", "max_wordpieces": 256, "needs": "nothing (Chroma's default ONNX model, downloaded once)"},
    "bge-small": {"model": "BAAI/bge-small-en-v1.5", "max_wordpieces": 512, "needs": "pip install sentence-transformers, and the model download",
                  "query_prefix": "Represent this sentence for searching relevant passages: ", "doc_prefix": ""},
    "e5-small": {"model": "intfloat/e5-small-v2", "max_wordpieces": 512, "needs": "pip install sentence-transformers, and the model download",
                 "query_prefix": "query: ", "doc_prefix": "passage: "},
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


class PrefixedSentenceTransformer(EmbeddingFunction):
    """A sentence-transformers model with the query and document prefixes
    its training expects, normalized for cosine."""

    def __init__(self, model: str, query_prefix: str = "", doc_prefix: str = "", _model=None):
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(model)
        self.model_name, self.query_prefix, self.doc_prefix, self.model = model, query_prefix, doc_prefix, _model

    def _encode(self, texts):
        return [list(map(float, v)) for v in self.model.encode(list(texts), normalize_embeddings=True)]

    def __call__(self, input):
        return self._encode(self.doc_prefix + t for t in input)

    def embed_query(self, input):
        return self._encode(self.query_prefix + t for t in input)

    @staticmethod
    def name():
        return "prefixed-sentence-transformer"

    def get_config(self):
        return {"model": self.model_name, "query_prefix": self.query_prefix, "doc_prefix": self.doc_prefix}

    @staticmethod
    def build_from_config(config):
        return PrefixedSentenceTransformer(config["model"], config["query_prefix"], config["doc_prefix"])

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
        return PrefixedSentenceTransformer(arm["model"], arm["query_prefix"], arm["doc_prefix"]), arm["model"]
    except Exception as e:
        raise RuntimeError(f"{name} needs {arm['needs']} ({type(e).__name__}: {str(e)[:80]})") from e


MINILM_TOKENIZER = Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2" / "onnx" / "tokenizer.json"


def over_limit(texts, arm: str = DEFAULT):
    """(chunks over the arm's input limit, total), counted with the MiniLM
    tokenizer, which is the same WordPiece vocabulary bge-small and e5-small
    use. None when the arm has no limit or the tokenizer is not on disk."""
    limit = ARMS[arm]["max_wordpieces"]
    count = wordpiece_counter()
    texts = list(texts)
    if not limit or count is None:
        return None
    return sum(1 for n in count(texts) if n > limit - 2), len(texts)


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
