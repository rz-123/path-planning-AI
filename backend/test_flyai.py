"""
飞猪 FlyAI 数据查询测试脚本
===========================
测试飞猪 CLI 是否能查到真实的景点、酒店数据。

用法：
  cd backend
  python test_flyai.py

前提：已安装 flyai CLI 且 .env 中配置了 FLYAI_API_KEY
"""
import json
import subprocess
import os
import sys
from pathlib import Path


# Windows npm 全局安装路径
FLYAI_PATH = os.path.expanduser("~/AppData/Roaming/npm/flyai.cmd")
if not os.path.isfile(FLYAI_PATH):
    FLYAI_PATH = os.path.expanduser("~/AppData/Roaming/npm/flyai")
if not os.path.isfile(FLYAI_PATH):
    # 再试一下 PATH 查找
    import shutil
    FLYAI_PATH = shutil.which("flyai") or shutil.which("flyai.cmd") or "flyai"


def load_api_key() -> str:
    """从 .env 文件读取 FLYAI_API_KEY"""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        print(f"[错误] 找不到 .env 文件: {env_path}")
        sys.exit(1)

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("FLYAI_API_KEY="):
            return line.split("=", 1)[1]
    print("[错误] .env 中未配置 FLYAI_API_KEY")
    sys.exit(1)


def run_flyai(cmd: list, timeout: int = 30) -> dict:
    """执行 flyai 命令并解析 JSON 返回"""
    # 替换 flyai 为完整路径
    cmd = [FLYAI_PATH if c == "flyai" else c for c in cmd]
    env = os.environ.copy()
    env["FLYAI_API_KEY"] = load_api_key()
    try:
        r = subprocess.run(cmd, capture_output=True, text=False, timeout=timeout, env=env)
        out = r.stdout.decode("utf-8", errors="replace").strip()
        # 找到第一个 { 和最后一个 } 之间的内容（忽略额外输出）
        start = out.find("{")
        end = out.rfind("}")
        if start >= 0 and end > start:
            out = out[start:end + 1]
        return json.loads(out)
    except FileNotFoundError:
        return {"error": f"flyai 命令未找到: {cmd[0]}"}
    except json.JSONDecodeError as e:
        return {"error": f"JSON解析失败: {e}", "raw": out[:500] if 'out' in dir() else ""}
    except subprocess.TimeoutExpired:
        return {"error": "请求超时"}
    except Exception as e:
        return {"error": str(e)}


def test_search_poi():
    """测试景点搜索 search-poi"""
    print("=" * 60)
    print("1. 搜索景点: search-poi")
    print("=" * 60)

    data = run_flyai(["flyai", "search-poi", "--city-name", "北京", "--keyword", "故宫"])
    if data.get("error"):
        print(f"  ❌ 失败: {data['error']}")
        return

    items = data.get("data", {}).get("itemList", [])
    print(f"  ✅ 成功! 查到 {len(items)} 个景点\n")

    for item in items[:5]:
        name = item.get("name", "?")
        addr = item.get("address", "?")
        cat = item.get("category", "?")
        lvl = item.get("poiLevel") or "未评级"
        lat, lng = item.get("latitude", "?"), item.get("longitude", "?")
        ticket = item.get("ticketInfo") or {}
        price = ticket.get("price", "未知")
        print(f"  景点: {name}")
        print(f"    地址: {addr} | 类别: {cat} | 等级: {lvl}")
        print(f"    坐标: {lat}, {lng} | 票价: {price}\n")


def test_search_hotel():
    """测试酒店搜索 search-hotel"""
    print("=" * 60)
    print("2. 搜索酒店: search-hotel")
    print("=" * 60)

    data = run_flyai([
        "flyai", "search-hotel",
        "--dest-name", "北京",
        "--check-in-date", "2026-07-10",
        "--check-out-date", "2026-07-12",
        "--hotel-stars", "3,4",
    ])
    if data.get("error"):
        print(f"  ❌ 失败: {data['error']}")
        return

    items = data.get("data", {}).get("itemList", [])
    print(f"  ✅ 成功! 查到 {len(items)} 个酒店\n")

    for item in items[:5]:
        name = item.get("name", "?")
        price = item.get("price", "?")
        star = item.get("star", "?")
        addr = item.get("address", "?")
        brand = item.get("brandName") or "无品牌"
        print(f"  酒店: {name}")
        print(f"    价格: {price} | 星级: {star} | 品牌: {brand}")
        print(f"    地址: {addr}\n")


def test_keyword_search():
    """测试关键词搜索 keyword-search"""
    print("=" * 60)
    print("3. 关键词搜索: keyword-search")
    print("=" * 60)

    data = run_flyai(["flyai", "keyword-search", "--query", "北京故宫门票"])
    if data.get("error"):
        print(f"  ❌ 失败: {data['error']}")
        return

    items = data.get("data", {}).get("itemList", [])
    print(f"  ✅ 成功! 查到 {len(items)} 条商品\n")

    for item in items[:5]:
        info = item.get("info", {})
        title = info.get("title", "?")
        price = info.get("price") or "未知"
        print(f"  商品: {title}")
        print(f"    价格: {price}\n")


def test_multi_city():
    """测试多个城市"""
    print("=" * 60)
    print("4. 多城市景点搜索")
    print("=" * 60)

    tests = [("杭州", "西湖"), ("成都", "熊猫"), ("西安", "兵马俑"), ("上海", "外滩")]
    for city, kw in tests:
        data = run_flyai(["flyai", "search-poi", "--city-name", city, "--keyword", kw])
        items = data.get("data", {}).get("itemList", [])
        names = [i.get("name", "?") for i in items[:3]]
        status = "✅" if items else "⚠️"
        print(f"  {status} {city} ({kw}): {len(items)} 条 → {', '.join(names)}")
    print()


def test_current_code_issue():
    """验证当前代码中的调用方式"""
    print("=" * 60)
    print("5. 验证 tools.py 当前调用方式")
    print("=" * 60)

    # 当前代码调用
    print("  [当前代码] flyai keyword-search --query X --type poi")
    data = run_flyai(["flyai", "keyword-search", "--query", "北京故宫", "--type", "poi"])
    if data.get("error") and "unknown option" in str(data.get("error")):
        print("  ❌ 失败: --type 参数不被 keyword-search 支持\n")
    else:
        print(f"  ⚠️ 返回 {len(data.get('data',{}).get('itemList',[]))} 条\n")

    # 正确调用方式
    print("  [正确方式] flyai search-poi --city-name X --keyword Y")
    print("  [正确方式] flyai search-hotel --dest-name X --check-in-date ...")
    print()


if __name__ == "__main__":
    print("\n" + "╔════════════════════════════════════╗")
    print("║     飞猪 FlyAI 数据查询测试        ║")
    print("╚════════════════════════════════════╝\n")

    if not os.path.isfile(FLYAI_PATH) and FLYAI_PATH == "flyai":
        print(f"[警告] 未找到 flyai 可执行文件")
        print(f"        PATH: {os.environ.get('PATH', '')[:200]}")
    else:
        print(f"[信息] flyai 路径: {FLYAI_PATH}")

    print(f"[信息] API Key: {load_api_key()[:10]}...\n")

    test_search_poi()
    test_search_hotel()
    test_keyword_search()
    test_multi_city()
    test_current_code_issue()

    print("=" * 60)
    print("全部测试完成!")
    print("=" * 60)
