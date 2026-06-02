"""
Usage: python scripts/search_test.py <query> [top_k] [--full]
Example: python scripts/search_test.py "LDPC 编码" 3 --full
"""
import sys, asyncio, httpx

PORT = 8765
USERNAME = "testuser2"
PASSWORD = "test123456"


async def search(query, top_k=3, show_full=False):
    async with httpx.AsyncClient(timeout=180) as c:
        # Login
        r = await c.post(f"http://127.0.0.1:{PORT}/api/auth/login",
                         json={"username": USERNAME, "password": PASSWORD})
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        # Search
        r = await c.get(f"http://127.0.0.1:{PORT}/api/knowledge/search",
                        params={"query": query, "top_k": top_k}, headers=h)
        results = r.json()["results"]

        print(f"\nQuery: {query}")
        print(f"Results: {len(results)}\n")

        for i, rr in enumerate(results):
            header = rr["content"].split("\n")[0][:100]
            content = rr["content"]
            print(f"{'='*60}")
            print(f"[{i+1}] {rr['source'][:80]}")
            print(f"    Score: {rr['score']:.4f}  |  Length: {len(content)} chars")
            print(f"    Header: {header}")
            print(f"{'='*60}")
            if show_full:
                print(content)
            else:
                print(content[:500])
                if len(content) > 500:
                    print(f"\n    ... ({len(content) - 500} more chars) ...")
            print()


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "OFDM"
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    show_full = "--full" in sys.argv
    asyncio.run(search(query, top_k, show_full))
