import yaml
import httpx
import asyncio
from pathlib import Path

CONFIG_PATH = Path("config/nodes.yaml")

async def check_node_health(node):
    url = f"{node['url']}/api/tags"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            res = await client.get(url)
            if res.status_code == 200:
                print(f"[HEALTH] Node {node['name']} is ONLINE.")
                return True
        except Exception:
            pass
    print(f"[HEALTH] Node {node['name']} is OFFLINE.")
    return False

async def monitor_loop():
    while True:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r") as f:
                data = yaml.safe_load(f)
            nodes = data.get("nodes", [])
            for node in nodes:
                await check_node_health(node)
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(monitor_loop())
