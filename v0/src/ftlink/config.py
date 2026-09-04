from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource


class DocumentCfg(BaseModel):
    pdf_path: Path
    summary_pages: tuple[int, int] = Field(description="inclusive 1-based PDF page range")
    footnote_no: int
    # document metadata is data, not code: it belongs here with the other targets
    company: str = ""
    period_end: str = ""
    currency: str = "TL"


class OcrCfg(BaseModel):
    dpi: int = 300
    psm: int = 4
    lang: str = "tur"
    # rate rows (percent cells) are re-read per cell by the second engine, which
    # unlike tesseract reads the % glyph on this scan class (measured 6/6 vs 0/6)
    percent_rescue: bool = True


class CandidatesCfg(BaseModel):
    rrf_k: float = 10.0
    anchor_weight: float = 3.0
    top_k: int = 8
    dense_model: str = "intfloat/multilingual-e5-small"
    # HF snapshot hash: the uv lockfile pins packages, not model weights; this does
    dense_model_revision: str = "614241f622f53c4eeff9890bdc4f31cfecc418b3"


class LlmCfg(BaseModel):
    enabled: bool = False
    base_url: str = "http://localhost:11434/v1"  # any OpenAI-compatible endpoint
    # placeholder endpoint default; the README's measured precision-1.00 result
    # used a 35B-class local model, so treat smaller defaults as unmeasured
    model: str = "llama3.1:8b"
    cache_path: Path = Path("cache/llm_calls.jsonl")


class LinkingCfg(BaseModel):
    cross_encoder_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    cross_encoder_revision: str = "1427fd652930e4ba29e8149678df786c240d8825"
    accept_threshold: float = 0.5
    # rank-aware acceptance floor: the top-ranked candidate is admitted when its
    # sigmoid clears this coarse guard (well below the operating threshold), since
    # absolute sigmoid scales vary across rerankers and rank is the validated signal
    rank1_min_score: float = 0.2
    # approach C (the deliberately insufficient lexical baseline) acceptance bar
    lexical_threshold: float = 0.75
    llm: LlmCfg = LlmCfg()


class ConfidenceCfg(BaseModel):
    low_confidence_flag: float = 0.5
    second_engine: bool = True  # RapidOCR digit cross-check (flag over fix)
    # pages whose footnote-referencing rows serve as EXTRA calibration controls
    # (e.g. the cash-flow statement); they never enter the output, they only give
    # the runtime Platt fit more document-derived positives/negatives
    extra_control_pages: list[int] = []


class OutputCfg(BaseModel):
    dir: Path = Path("outputs")
    emit_report_html: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FTLINK_", env_nested_delimiter="__")

    document: DocumentCfg
    ocr: OcrCfg = OcrCfg()
    candidates: CandidatesCfg = CandidatesCfg()
    linking: LinkingCfg = LinkingCfg()
    confidence: ConfidenceCfg = ConfidenceCfg()
    output: OutputCfg = OutputCfg()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Settings":
        class _WithYaml(cls):  # type: ignore[misc]
            @classmethod
            def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
                # precedence: init > env > yaml
                return (init_settings, env_settings, YamlConfigSettingsSource(settings_cls, yaml_file=Path(path)))

        return _WithYaml()  # type: ignore[call-arg]
