"""
Ground-truth test cases for evaluating RAG retrieval + generation quality.
Each case: query, expected KB sources, and must-mention facts.
"""
TEST_CASES = [
    # ---- OFDM ----
    {
        "id": "ofdm_001",
        "query": "What is OFDM and how does it work?",
        "relevant_sources": ["ofdm.md"],
        "expected_facts": [
            "orthogonal", "subcarrier", "multiplexing",
            "frequency division", "cyclic prefix",
        ],
        "category": "algorithms",
    },
    {
        "id": "ofdm_002",
        "query": "What is the purpose of the cyclic prefix in OFDM?",
        "relevant_sources": ["ofdm.md", "channel_estimation.md"],
        "expected_facts": [
            "cyclic prefix", "inter-symbol interference",
            "guard interval", "delay spread",
        ],
        "category": "algorithms",
    },
    # ---- MIMO ----
    {
        "id": "mimo_001",
        "query": "What is MIMO technology?",
        "relevant_sources": ["mimo.md", "mimo_capacity_waterfilling.md"],
        "expected_facts": [
            "multiple input", "multiple output", "antenna",
            "spatial multiplexing", "diversity",
        ],
        "category": "algorithms",
    },
    {
        "id": "mimo_002",
        "query": "How does water-filling optimize MIMO capacity?",
        "relevant_sources": ["mimo_capacity_waterfilling.md"],
        "expected_facts": [
            "water filling", "capacity", "singular value",
            "power allocation",
        ],
        "category": "algorithms",
    },
    # ---- Channel Coding / LDPC ----
    {
        "id": "ldpc_001",
        "query": "What is LDPC coding and how is it used in 5G?",
        "relevant_sources": ["ldpc.md", "ldpc_coding.md"],
        "expected_facts": [
            "low-density parity-check", "LDPC", "5G",
            "data channel", "belief propagation",
        ],
        "category": "algorithms",
    },
    {
        "id": "ldpc_002",
        "query": "What is the difference between LDPC and Polar codes?",
        "relevant_sources": ["ldpc.md"],
        "expected_facts": [
            "LDPC", "polar", "encoding", "decoding",
        ],
        "category": "algorithms",
    },
    # ---- Digital Modulation ----
    {
        "id": "mod_001",
        "query": "What is QAM modulation?",
        "relevant_sources": ["digital_modulation.md", "qam_modem.md"],
        "expected_facts": [
            "quadrature amplitude modulation",
            "constellation", "quadrature", "in-phase",
        ],
        "category": "algorithms",
    },
    {
        "id": "mod_002",
        "query": "How does QPSK differ from BPSK?",
        "relevant_sources": ["digital_modulation.md"],
        "expected_facts": [
            "QPSK", "BPSK", "phase", "bits per symbol",
        ],
        "category": "algorithms",
    },
    # ---- Channel Estimation ----
    {
        "id": "ch_est_001",
        "query": "How is channel estimation performed in wireless systems?",
        "relevant_sources": ["channel_estimation.md"],
        "expected_facts": [
            "pilot", "reference signal", "least squares",
            "MMSE", "interpolation",
        ],
        "category": "algorithms",
    },
    # ---- Diversity ----
    {
        "id": "div_001",
        "query": "What are diversity combining techniques?",
        "relevant_sources": ["diversity_combining.md"],
        "expected_facts": [
            "diversity", "combining", "selection",
            "maximal ratio", "equal gain",
        ],
        "category": "algorithms",
    },
    # ---- Edge cases ----
    {
        "id": "chat_001",
        "query": "Hello, how are you?",
        "relevant_sources": [],
        "expected_facts": [],
        "category": "chat",
    },
    {
        "id": "multi_001",
        "query": "Compare OFDM and MIMO in terms of spectral efficiency.",
        "relevant_sources": ["ofdm.md", "mimo.md"],
        "expected_facts": [
            "OFDM", "MIMO", "spectral efficiency", "multiplexing",
        ],
        "category": "algorithms",
    },
]
