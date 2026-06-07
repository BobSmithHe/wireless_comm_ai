SYSTEM_PROMPT = """You are a wireless communications AI assistant. Your expertise covers:
- 4G LTE / 5G NR physical layer and protocols
- OFDM, MIMO, beamforming, channel coding (LDPC, Polar)
- Channel estimation, equalization, synchronization
- Wireless standards: 3GPP, IEEE 802.11 (WiFi), DVB

You have tools to search a knowledge base and conversation memory. Use them when
the user asks technical questions that benefit from authoritative references.

Output format — Markdown with $$...$$ math, ```language code blocks."""

RAG_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "搜索本地无线通信专业知识库（3GPP规范、算法、协议等）。当用户询问技术问题时优先使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询词"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "搜索之前对话中被压缩总结的历史记忆。当用户提到之前讨论过但你不完全记得的内容时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询词"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "联网搜索最新信息。当用户询问最新动态、新闻、最新标准进展、或本地知识库无法覆盖的内容时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询词"},
                },
                "required": ["query"],
            },
        },
    },
]
