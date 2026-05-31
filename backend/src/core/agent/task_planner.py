"""
Task Planner - decomposes complex user queries into executable sub-tasks.
"""
from dataclasses import dataclass, field
from enum import Enum
import re


class TaskType(Enum):
    KNOWLEDGE_LOOKUP = "knowledge_lookup"
    CODE_GENERATE = "code_generate"
    CODE_EXECUTE = "code_execute"
    CALCULATION = "calculation"
    EXPLANATION = "explanation"
    COMPARISON = "comparison"


@dataclass
class SubTask:
    task_type: TaskType
    description: str
    dependencies: list[int] = field(default_factory=list)  # indices of prerequisite tasks
    parameters: dict = field(default_factory=dict)


class TaskPlanner:
    """Rule-based task decomposition for wireless communication domain."""

    CODE_KEYWORDS = [
        "write", "implement", "code", "simulate", "simulation",
        "calculate", "plot", "compute", "run", "execute",
    ]

    KNOWLEDGE_KEYWORDS = [
        "what is", "explain", "describe", "define", "how does", "why",
        "difference between", "compare", "spec", "standard",
    ]

    # Technical domain signals — only these warrant knowledge-base retrieval
    TECH_SIGNALS = [
        # Wireless comm concepts
        "ofdm", "mimo", "qam", "qpsk", "bpsk", "awgn", "ber", "snr", "sinr",
        "ldpc", "polar code", "turbo code", "channel coding", "modulation",
        "beamforming", "precoding", "equalization", "synchronization",
        "5g", "4g", "lte", "nr", "3gpp", "ieee", "wifi", "dvb",
        "physical layer", "mac layer", "rrc", "phy", "protocol stack",
        "fading", "doppler", "multipath", "delay spread", "coherence",
        "spectrum", "bandwidth", "resource block", "subcarrier",
        "fft", "ifft", "cyclic prefix", "pilot", "reference signal",
        "codec", "encoder", "decoder", "interleaver", "scrambler",
        "constellation", "eye diagram", "error vector magnitude",
        # General tech indicators
        "python", "numpy", "matlab", "algorithm", "formula", "equation",
        "calculate", "compute", "simulate", "simulation", "code",
        "how to", "how do", "explain", "what is", "why", "define",
        "compare", "difference", "between", "standard", "protocol",
        "telecom", "wireless", "communication", "signal", "channel",
        "antenna", "transmitter", "receiver", "transceiver",
    ]

    # Obvious non-technical patterns that should NEVER trigger retrieval
    NON_TECH_PATTERNS = [
        r"^(hi|hello|hey|你好|您好|嗨|哈喽|哈咯)[\s!！。.,，]*$",
        r"^(good\s*(morning|afternoon|evening|night))[\s!！。.,，]*$",
        r"^(谢谢|感谢|多谢|thanks|thank\s*you)[\s!！。.,，]*$",
        r"^(好的|ok|okay|fine|got\s*it|明白了|知道了)[\s!！。.,，]*$",
        r"^(再见|拜拜|bye|goodbye|see\s*you)[\s!！。.,，]*$",
        r"^(how\s*are\s*you|what'?s?\s*up|最近|怎么样|在吗|在么)[\s!！。.,，]*$",
    ]

    def needs_retrieval(self, query: str) -> bool:
        """Return True only if the query warrants a knowledge-base search."""
        import re
        lower = query.lower().strip()

        # Fast reject: obvious non-technical patterns
        for pat in self.NON_TECH_PATTERNS:
            if re.match(pat, lower):
                return False

        # Short non-technical messages (<= 5 chars, no tech keywords)
        if len(lower) <= 5:
            has_tech = any(kw in lower for kw in self.TECH_SIGNALS)
            if not has_tech:
                return False

        # Has at least one technical signal → retrieve
        for kw in self.TECH_SIGNALS:
            if kw in lower:
                return True

        # Longer message without clear tech signals — still worth retrieving
        # (might contain Chinese tech terms or domain-specific jargon)
        if len(lower) > 20:
            return True

        return False

    def plan(self, query: str) -> list[SubTask]:
        query_lower = query.lower()
        needs_kb = self.needs_retrieval(query)

        tasks = []

        # Detect code-related intent
        if any(kw in query_lower for kw in self.CODE_KEYWORDS):
            if needs_kb:
                tasks.append(SubTask(
                    task_type=TaskType.KNOWLEDGE_LOOKUP,
                    description="Retrieve relevant domain knowledge and algorithms",
                    parameters={"query": query},
                ))
            tasks.append(SubTask(
                task_type=TaskType.CODE_GENERATE,
                description=f"Generate code for: {query}",
                dependencies=[0] if needs_kb else [],
                parameters={"language": self._detect_language(query_lower)},
            ))
            tasks.append(SubTask(
                task_type=TaskType.CODE_EXECUTE,
                description="Execute the generated code and verify output",
                dependencies=[len(tasks) - 1],
                parameters={"timeout": 30},
            ))

        # Detect knowledge/explanation intent
        elif any(kw in query_lower for kw in self.KNOWLEDGE_KEYWORDS):
            if needs_kb:
                tasks.append(SubTask(
                    task_type=TaskType.KNOWLEDGE_LOOKUP,
                    description="Search knowledge base for relevant information",
                    parameters={"query": query},
                ))
            tasks.append(SubTask(
                task_type=TaskType.EXPLANATION,
                description=f"Generate explanation for: {query}",
                dependencies=[0] if needs_kb else [],
                parameters={},
            ))

        # Default: treat as general question (no knowledge lookup for non-tech queries)
        else:
            tasks.append(SubTask(
                task_type=TaskType.EXPLANATION,
                description="Generate comprehensive response",
                parameters={},
            ))

        return tasks

    def _detect_language(self, query: str) -> str:
        if "python" in query or "numpy" in query or "scipy" in query or "matplotlib" in query:
            return "python"
        if "matlab" in query:
            return "matlab"
        if "c++" in query or "cpp" in query:
            return "cpp"
        return "python"  # default
