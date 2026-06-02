# md_splitter.py
import re
import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple
import json
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        RecursiveCharacterTextSplitter = None
        logger.warning("langchain_text_splitters not installed, large chunks will not be split. Install: pip install langchain-text-splitters")


@dataclass
class Chunk:
    content: str
    metadata: Dict[str, Any]
    chunk_type: str = "header"
    chunk_id: str = ""


class SmartMarkdownSplitter:
    SIZE_BINDS = (300, 500, 800, 1200, 1500)

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        max_chunk_size: int = 2000,
        min_chunk_size: int = 200,
        protect_code_blocks: bool = True,
        protect_tables: bool = True,
        keep_headers_in_content: bool = True,
        add_full_header_on_subchunk: bool = True
    ):
        self.headers_to_split_on = [("#", "H1"), ("##", "H2"), ("###", "H3"), ("####", "H4"), ("#####", "H5")]
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.protect_code_blocks = protect_code_blocks
        self.protect_tables = protect_tables
        self.keep_headers_in_content = keep_headers_in_content
        self.add_full_header_on_subchunk = add_full_header_on_subchunk

        self.code_block_pattern = re.compile(r'```[\s\S]*?```', re.MULTILINE)
        self.header_pattern = re.compile(r'^(#{1,6})\s*(.+)$', re.MULTILINE)

    def _protect_special_content(self, text: str) -> Tuple[str, Dict[str, List[str]]]:
        protected = {"code_blocks": [], "tables": []}
        res = text
        if self.protect_code_blocks:
            cb_list = []
            def cb_rep(m):
                pl = f"__CODE_{len(cb_list)}__"
                cb_list.append(m.group(0))
                return pl
            res = self.code_block_pattern.sub(cb_rep, res)
            protected["code_blocks"] = cb_list

        if self.protect_tables:
            lines = res.split("\n")
            new_lines, tb_buf, tb_list = [], [], []
            in_tb = False
            for line in lines:
                s = line.strip()
                if s.startswith("|") and "|" in s[1:]:
                    in_tb = True
                    tb_buf.append(line)
                else:
                    if in_tb:
                        pl = f"__TABLE_{len(tb_list)}__"
                        tb_list.append("\n".join(tb_buf))
                        new_lines.append(pl)
                        tb_buf, in_tb = [], False
                    new_lines.append(line)
            if in_tb and tb_buf:
                pl = f"__TABLE_{len(tb_list)}__"
                tb_list.append("\n".join(tb_buf))
                new_lines.append(pl)
            res = "\n".join(new_lines)
            protected["tables"] = tb_list
        return res, protected

    def _restore_special_content(self, text: str, pd: Dict):
        res = text
        for idx, val in enumerate(pd["code_blocks"]):
            res = res.replace(f"__CODE_{idx}__", val)
        for idx, val in enumerate(pd["tables"]):
            res = res.replace(f"__TABLE_{idx}__", val)
        return res

    def _split_by_headers(self, text: str) -> List[Dict]:
        lines = text.split("\n")
        chunks = []
        cur_meta = {}
        cur_content = []
        for line in lines:
            m = re.match(r'^(#{1,6})\s+(.+)', line)
            if m:
                level = len(m.group(1))
                body = m.group(2).strip()
                h_key = f"H{level}"
                if cur_content:
                    txt = "\n".join(cur_content).strip()
                    if txt:
                        chunks.append({"content": txt, "metadata": cur_meta.copy()})
                new_meta = {k: v for k, v in cur_meta.items() if k.startswith("H") and int(k[1:]) < level}
                new_meta[h_key] = body
                chain = []
                for lv in range(1, level + 1):
                    k = f"H{lv}"
                    if k in new_meta:
                        chain.append(new_meta[k])
                new_meta["parent_title_key"] = ">".join(chain)
                cur_meta = new_meta
                cur_content = [line] if self.keep_headers_in_content else []
            else:
                cur_content.append(line)
        if cur_content:
            txt = "\n".join(cur_content).strip()
            if txt:
                chunks.append({"content": txt, "metadata": cur_meta.copy()})
        return chunks

    def _build_header_prefix(self, meta:Dict):
        if not self.keep_headers_in_content:
            return ""
        buf = []
        for lv in range(1,7):
            k = f"H{lv}"
            if k in meta and meta[k]:
                buf.append(f"{'#'*lv} {meta[k]}")
        return "\n".join(buf)

    def _needs_further_splitting(self, text:str, meta):
        if len(text) > self.max_chunk_size:
            return True
        if text.count("\n\n")>5:
            return True
        if len(re.findall(r"\n#{2,6}\s*",text))>1:
            return True
        return False

    def _recursive_split(self, text:str, meta:Dict):
        if RecursiveCharacterTextSplitter is None:
            raise RuntimeError("缺少langchain")
        if self.add_full_header_on_subchunk:
            raw = text.splitlines()
            if raw and raw[0].lstrip().startswith(("#","##","###")):
                raw = raw[1:]
                text = "\n".join(raw)
        pro_txt, pro_dict = self._protect_special_content(text)
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n","\n","(?<=。)","(?<=！)","(?<=？)","(?<=;)","(?<=\.\s)","(?<=\?)","(?<=!)","(?<=；)","(?<=，)","(?<=,\s)"," ",""],
            is_separator_regex=True
        )
        docs = splitter.create_documents([pro_txt])
        total = len(docs)
        pre = self._build_header_prefix(meta) if self.add_full_header_on_subchunk else ""
        res = []
        for idx, d in enumerate(docs):
            restore = self._restore_special_content(d.page_content, pro_dict)
            full_txt = f"{pre}\n{restore}".strip() if pre else restore.strip()
            new_meta = meta.copy()
            new_meta["sub_chunk"] = idx+1
            new_meta["total_sub_chunks"] = total
            res.append({"content":full_txt,"metadata":new_meta})
        return res

    def split_text(self, text:str)->List[Chunk]:
        if not isinstance(text,str) or not text.strip():
            return []
        all_chunk = []
        header_blks = self._split_by_headers(text)
        for blk in header_blks:
            cont = blk["content"]
            meta = blk["metadata"]
            if not self._needs_further_splitting(cont, meta):
                mid = uuid.uuid4().hex
                std_meta = meta.copy()
                std_meta["sub_chunk"]=1
                std_meta["total_sub_chunks"]=1
                all_chunk.append(Chunk(content=cont,metadata=std_meta,chunk_type="single_sub",chunk_id=mid))
            else:
                try:
                    subs = self._recursive_split(cont,meta)
                    for sub in subs:
                        mid = uuid.uuid4().hex
                        all_chunk.append(Chunk(content=sub["content"],metadata=sub["metadata"],chunk_type="multi_sub",chunk_id=mid))
                except Exception as e:
                    logger.warning("chunk split failed (size=%d): %s, storing as err_sub", len(cont), e)
                    mid = uuid.uuid4().hex
                    std_meta = meta.copy()
                    std_meta["sub_chunk"]=1
                    std_meta["total_sub_chunks"]=1
                    all_chunk.append(Chunk(content=cont,metadata=std_meta,chunk_type="err_sub",chunk_id=mid))
        return all_chunk