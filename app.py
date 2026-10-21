import json
from pathlib import Path
from flask import Flask, render_template_string, request

CACHE_FILE = Path(__file__).with_name("ufc_lw_fw_fights.json")
MAX_STEPS = 5

app = Flask(__name__)


def is_winner(value):
    return value is True or str(value).lower() == "true"


def build_graph(fights):
    graph = {}
    names = {}

    for fight in fights:
        fighters = fight.get("fighters", {})
        first = fighters.get("first", {})
        second = fighters.get("second", {})

        first_id = first.get("id")
        second_id = second.get("id")
        first_name = first.get("name")
        second_name = second.get("name")

        if not all([first_id, second_id, first_name, second_name]):
            continue

        names[first_id] = first_name
        names[second_id] = second_name

        if is_winner(first.get("winner")):
            winner_id, loser_id = first_id, second_id
        elif is_winner(second.get("winner")):
            winner_id, loser_id = second_id, first_id
        else:
            continue

        graph.setdefault(winner_id, set()).add(loser_id)

    return graph, names


def find_fighter_id_fuzzy(name, names):
    """支持模糊匹配：只要输入的关键字包含在选手全名里即可"""
    typed = name.strip().lower()
    if not typed:
        return None

    # 1. 完全精确匹配
    for fighter_id, fighter_name in names.items():
        if fighter_name.lower() == typed:
            return fighter_id

    # 2. 包含关键字匹配
    for fighter_id, fighter_name in names.items():
        if typed in fighter_name.lower():
            return fighter_id

    return None


def find_paths(graph, start_id, target_id):
    paths = []

    def search(current_id, path):
        if current_id == target_id:
            paths.append(path)
            return

        if len(path) - 1 >= MAX_STEPS:
            return

        for next_id in graph.get(current_id, set()):
            if next_id not in path:
                search(next_id, path + [next_id])

    search(start_id, [start_id])
    return paths


# 启动加载数据
if not CACHE_FILE.exists():
    raise FileNotFoundError(
        "找不到 ufc_lw_fw_fights.json，请先运行 mma_test.py！"
    )

fights = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
graph, names = build_graph(fights)
fighter_names = sorted(names.values())


PAGE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UFC 选手叠盒子计算器</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Arial, "Microsoft YaHei", sans-serif;
      background: #0d0f12;
      color: #f5f5f5;
    }
    main {
      width: min(900px, calc(100% - 32px));
      margin: 0 auto;
      padding: 48px 0;
    }
    .tag {
      color: #ff4d37;
      font-size: 13px;
      font-weight: bold;
      letter-spacing: 2px;
    }
    h1 {
      margin: 12px 0;
      font-size: clamp(30px, 6vw, 54px);
    }
    .intro { color: #aeb5bf; line-height: 1.7; }
    .panel {
      margin-top: 28px;
      padding: 28px;
      border: 1px solid #303640;
      border-radius: 18px;
      background: #161a20;
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    }
    form { display: grid; grid-template-columns: 1fr 1fr auto; gap: 14px; }
    input, button {
      border: 0;
      border-radius: 10px;
      font-size: 16px;
      padding: 14px;
    }
    input { background: #272d36; color: white; outline: none; }
    input:focus { border: 1px solid #ff4d37; }
    button {
      cursor: pointer;
      background: #ff4d37;
      color: white;
      font-weight: bold;
    }
    button:hover { background: #ff3219; }
    .notice, .result {
      margin-top: 24px;
      padding: 18px;
      border-radius: 12px;
    }
    .notice { background: #33211e; color: #ffb7a9; border: 1px solid #5c2c26; }
    .result { background: #202731; border: 1px solid #2e3846; }
    .path {
      padding: 12px 0;
      border-bottom: 1px solid #343b45;
      color: #e9edf3;
      line-height: 1.6;
      font-size: 15px;
    }
    .path:last-child { border-bottom: 0; }
    .muted { color: #9da6b2; }
    @media (max-width: 700px) {
      form { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <div class="tag">UFC MMA MATH CALCULATOR</div>
    <h1>叠盒子计算器</h1>
    <p class="intro">
      输入两名选手（支持输入部分姓氏），查询 A 通过最多 {{ max_steps }} 场胜负关系“叠盒子赢” Z 的所有逻辑链条。
    </p>

    <section class="panel">
      <form method="post">
        <input list="fighters" name="start" placeholder="选手 A (例如 Volkanovski)"
                value="{{ start }}" required>
        <input list="fighters" name="target" placeholder="选手 Z (例如 Gaethje)"
                value="{{ target }}" required>
        <button type="submit">开始计算</button>
      </form>

      <datalist id="fighters">
        {% for fighter in fighter_names %}
        <option value="{{ fighter }}">
        {% endfor %}
      </datalist>

      {% if error %}
      <div class="notice">{{ error }}</div>
      {% endif %}

      {% if matched_start and matched_target %}
      <div style="margin-top: 15px; color: #8892b0; font-size: 14px;">
        🎯 识别选手：<strong>{{ matched_start }}</strong> vs <strong>{{ matched_target }}</strong>
      </div>
      {% endif %}

      {% if paths is not none %}
      <div class="result">
        <strong style="font-size: 17px;">找到 {{ paths|length }} 条路径（最多 {{ max_steps }} 步）：</strong>
        <div style="margin-top: 12px;"></div>
        {% if paths %}
          {% for path in paths %}
          <div class="path"><strong>#{{ loop.index }}</strong>: {{ path|join(" → ") }}</div>
          {% endfor %}
        {% else %}
          <p class="muted" style="margin: 4px 0 0 0;">未能在 {{ max_steps }} 步内找到 {{ matched_start }} 赢 {{ matched_target }} 的路径。</p>
          {% if rev_paths %}
          <div style="margin-top: 15px; padding-top: 12px; border-top: 1px dashed #444;">
            <p style="color: #ff9d00;">💡 提示：顺向没找到，但找到了 <strong>{{ matched_target }}</strong> 反向叠盒子赢 <strong>{{ matched_start }}</strong> 的路径：</p>
            {% for rpath in rev_paths %}
            <div class="path" style="color: #ccc;">{{ loop.index }}. {{ rpath|join(" → ") }}</div>
            {% endfor %}
          </div>
          {% endif %}
        {% endif %}
      </div>
      {% endif %}
    </section>
  </main>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def home():
    start = ""
    target = ""
    error = ""
    paths = None
    rev_paths = None
    matched_start = ""
    matched_target = ""

    if request.method == "POST":
        start = request.form.get("start", "")
        target = request.form.get("target", "")

        start_id = find_fighter_id_fuzzy(start, names)
        target_id = find_fighter_id_fuzzy(target, names)

        if start_id is None or target_id is None:
            error = "未匹配到选手，请输入正确的名字或姓氏（如 Volkanovski）。"
        else:
            matched_start = names[start_id]
            matched_target = names[target_id]

            # 正向计算
            fighter_paths = find_paths(graph, start_id, target_id)
            paths = [
                [names[fid] for fid in path]
                for path in fighter_paths
            ]

            # 如果正向没找到，自动反向算一次作为温馨提示
            if not paths:
                reverse_fighter_paths = find_paths(graph, target_id, start_id)
                rev_paths = [
                    [names[fid] for fid in path]
                    for path in reverse_fighter_paths
                ]

    return render_template_string(
        PAGE,
        fighter_names=fighter_names,
        max_steps=MAX_STEPS,
        start=start,
        target=target,
        error=error,
        paths=paths,
        rev_paths=rev_paths,
        matched_start=matched_start,
        matched_target=matched_target,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)