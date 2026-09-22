# -*- coding: utf-8 -*-
"""056-A：从规则手册自动提取结构化规则参数 → AI-Collab/rule_contract.json。

用法：python extract_rule_contract.py [--manual <路径>] [--out <路径>]
- 读取 01-rules/投资规则手册_v*.md（取最新版本），正则提取关键阈值；
- 提取失败项 → 保留内置默认值并 WARN（幂等，不阻塞）；
- 输出结构见 02-方案 2.2（rule_contract.json 由 realtime_relay --distribute 刷新）。

================================================================================
v4.5.17（2026-09-22）· 结构性重构 —— 起因是一次静默改写了阈值的实发事故
================================================================================
🔴 **事故**：`e4_monthly_net_cap` 用 `re.search` **全文取首匹配**，抓到手册 §4.2.1 正文里的
   一句引用（「…现金出口被 **§1.4** 堵死」→ `1`），而真定义在 §4.3 行 341 的 `≤¥1,500`。
   契约 `warns: []`、本脚本自报「33 keys」一切正常 ⇒ **一个坏值静默覆盖内置默认并持续生效**
   （后果：卫星层**恒拦**，含 10/1 月度重置之后）。

本次不再「把那条正则改好就收工」（那正是 v4.5.6 说的**改数据不改机制**），而是改档案形状：

  ① **锚定提取**：阈值定义行在手册里是结构化行（`- **E4 卫星月净投入 ≤¥1,500**`）。
     对已核实的「定义行」键，正则**必须行首匹配**（`re.MULTILINE`）——
     正文里的引用永远不以 `- **E4 …` 开头 ⇒ **结构上不可能被顶替**。
  ② **合理性区间**：抽出的值必须落在该键的合理区间内（区间与内置默认同锚，见 `rule_keys`）。
     **越界 ⇒ 拒收 + 回退 builtin + 落 `sanity_rejected` + 落 `warns`**。
     这是与 ① **互相独立**的第二道防线：即使锚定被后人改坏，`1` 也当场被拒。
  ③ **来源留痕**：每个键记录它**取自手册第几行、原文是什么、是锚定命中还是兜底命中**
     （契约新增 `sources` 段）。⇒ 今后「阈值被悄悄改了」会**当场可见**，
     而不是等几个月后有人发现闸门不对劲。
  ④ **唯一真源**：键名 / 正则 / 内置默认 / 合理区间**全部来自 `rule_keys.py`**，
     本文件不再自己维护一份 `DEFAULTS`（原先同一阈值最多四处各写一遍）。
  ⑤ **接上一个「有人读、却从来没人写」的键**：`scorecard_max`
     （`Anchor-Software/app/.../report_service.py:551` 一直在读，契约里却从不存在 ⇒ 软件永远吃兜底 5）。

⚠️ **`extract(text) -> (rules, warns)` 签名与语义保持不变**（既有测试依赖），
   需要来源信息请用 `extract_full()`。
================================================================================
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rule_keys  # noqa: E402  ← 单一真源（v4.5.17）

#: 保留旧名（既有调用方 / 测试按此名引用）；**值由注册表派生，⛔ 不得在此另立一份**
DEFAULTS = rule_keys.defaults()

# 规则手册路径（默认取 01-rules 下最新 v*）
RULES_DIR = Path(__file__).resolve().parents[1] / "01-rules"


def latest_manual() -> Path:
    candidates = sorted(RULES_DIR.glob("投资规则手册_v*.md"), key=lambda p: p.name)
    if not candidates:
        raise FileNotFoundError(f"未找到规则手册：{RULES_DIR}")
    return candidates[-1]


# ══════════════════════════════════════════════════════════════════════════════
# 取值 / 定位工具
# ══════════════════════════════════════════════════════════════════════════════

def _lit(s: str):
    """解析 `const:` 字面量。"""
    if s in ("True", "False"):
        return s == "True"
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


#: 合法的 `conv` 标签 —— **归注册表所有**（`rule_keys.CONV_TAGS`），此处仅为旧名保留
CONV_TAGS = rule_keys.CONV_TAGS


def _conv(tag: str, m):
    """按 `conv` 标签从匹配对象取值。

    🔴 **未登记的标签不得静默跳过** —— v4.5.17 自曝：`scorecard_max` 的 `conv` 误写成 `"g2"`
    （应为 `"g2int"`），`_conv` 抛 `ValueError` 被 `except: continue` 吞掉 ⇒
    **表现为「正则没匹配上」**，而真相是「标签名写错了」——
    与 v4.5.5／v4.5.6「用错码／用错端点被读成『无源』」**同族**：
    **一个编程错误伪装成一次数据缺失。** 故未知标签改抛 `KeyError`（不被吞）。
    """
    if tag not in CONV_TAGS and not tag.startswith("const:"):
        raise KeyError(f"未知 conv 标签 {tag!r} —— 合法标签见 CONV_TAGS（这不是「没匹配上」，是标签写错）")
    if tag == "money":
        return int(m.group(1).replace(",", "").replace("，", ""))
    if tag == "int":
        return int(m.group(1))
    if tag == "float":
        return float(m.group(1))
    if tag == "g2int":
        return int(m.group(2))
    if tag == "g2float":
        return float(m.group(2))
    if tag == "text":
        return m.group(1)
    if tag.startswith("const:"):
        return _lit(tag[6:])
    raise ValueError(f"未知 conv: {tag}")


def _loc(text: str, start: int):
    """`(行号, 该行原文截断)` —— 来源留痕用（1-based 行号）。"""
    line = text.count("\n", 0, start) + 1
    ls = text.rfind("\n", 0, start) + 1
    le = text.find("\n", start)
    if le == -1:
        le = len(text)
    return line, text[ls:le].strip()[:160]


class Extractor:
    """一次提取的全部状态：rules / warns / sources / sanity_rejected / warn_details。

    ⚠️ `warns` **保持「裸键名列表」的旧契约**（既有测试与消费方按精确成员判断），
       失败原因另放 `warn_details` —— 增强不能以破坏既有契约为代价。
    """

    def __init__(self, text: str):
        self.text = text
        self.rules: dict = {}
        self.warns: list = []
        self.warn_details: dict = {}
        self.sources: dict = {}
        self.rejected: dict = {}

    # ---- 内部：统一的「记一次失败」----
    def _fail(self, name, reason):
        self.warns.append(name)
        self.warn_details[name] = reason

    def _ok(self, name, value, line, snippet, tier):
        self.rules[name] = value
        self.sources[name] = {"line": line, "text": snippet, "tier": tier}

    # ---- 主入口：按注册表提取一个标量键 ----
    def grab_spec(self, name: str, spec: dict) -> None:
        for pat, anchored in spec.get("patterns") or []:
            m = re.search(pat, self.text, re.MULTILINE if anchored else 0)
            if not m:
                continue
            try:
                val = _conv(spec["conv"], m)
            except ValueError:
                # 唯一的「数据问题」：抽到了数字但转换不了（如 `int("—")`）
                # ⇒ 换下一个模式是合理的。
                # 🔴 而 `TypeError` / `IndexError`（捕获组数量与 `conv` 对不上）
                #    **是编程错误，不得吞** —— v4.5.17 自曝：`conv` 误写导致 `IndexError`，
                #    被这里吞掉后**表现为「正则没匹配上」**，
                #    与 v4.5.5／v4.5.6「用错码／用错端点被读成『无源』」同族。
                continue

            line, snippet = _loc(self.text, m.start())
            lo, hi = spec.get("lo"), spec.get("hi")

            # 🔴 第二道防线：合理性区间（与锚定互相独立）
            if lo is not None and not (lo <= val <= hi):
                self.rejected[name] = {"value": val, "line": line, "text": snippet,
                                       "range": [lo, hi], "pattern": pat}
                self._fail(name,
                           f"🔴 抽取值 {val!r} 越界区间 [{lo}, {hi}]（来自手册行 {line}："
                           f"{snippet[:80]!r}）⇒ 已拒收，回退内置默认 {spec['builtin']!r}")
                self._ok(name, spec["builtin"], None, "（拒收回退 builtin）", "rejected")
                return

            self._ok(name, val, line, snippet, "anchored" if anchored else "fallback")
            return

        # 未命中任何模式
        if spec.get("anchor_required"):
            self._fail(name,
                       "🔴 锚定提取失败 —— 手册中**没有以行首形式出现的定义行** ⇒ "
                       "已回退内置默认。⛔ 本键**不许退回全文匹配**"
                       f"（E4 事故根因即「全文首匹配被正文引用顶替」）。请检查手册 {spec.get('manual')}")
        else:
            self._fail(name, "提取未命中任何模式 ⇒ 回退内置默认")
        self._ok(name, spec["builtin"], None, "（未命中，用 builtin）", "builtin")


def extract_full(text: str):
    """完整提取：返回 `(rules, warns, sources, sanity_rejected, warn_details)`。"""
    # 🔴 加载期硬校验（编程错误 fail-loud，⛔ 不与「没匹配上」混为一谈）
    _errs = rule_keys.validate()
    if _errs:
        raise RuntimeError("rule_keys 注册表校验失败（这是编程错误，不是数据缺失）：\n  - "
                           + "\n  - ".join(_errs))
    ex = Extractor(text)

    # ── ① 标量键：全部来自注册表（键名/正则/默认/区间**只有一处定义**）──
    for name, spec in rule_keys.SCALAR_KEYS.items():
        ex.grab_spec(name, spec)

    # ── ② 存在性规则（不是取值，是「这条契约还在不在」）──
    #    `value` 缺省为 True（纯存在性断言）；给了 `value` 则**哨兵在 ⇒ 该值成立**
    #    （如 `watchlist_confirm_ma_period`：措辞在 ⇒ 周期即 5，不是从别处抽来的数字）。
    for name, spec in rule_keys.EXISTENCE_KEYS.items():
        val = spec.get("value", True)
        if spec["sentinel"] in text:
            ex._ok(name, val, None, f"sentinel={spec['sentinel']!r} 存在", "sentinel")
        else:
            ex._fail(name, f"🔴 哨兵句 {spec['sentinel']!r} 在手册中消失 ⇒ 规则可能已被删除或改写")
            ex._ok(name, spec["builtin"], None, "（哨兵缺失，用 builtin）", "builtin")

    # ── ③ 止盈档位（自定义：findall + 档位数守卫）──
    m_tp = re.findall(r"\+(\d{1,2})%\s*→\s*(再)?卖25%", text)
    if len(m_tp) >= 1:
        pos = re.search(r"\+(\d{1,2})%\s*→\s*(再)?卖25%", text)
        loc = _dict_loc(text, pos.start()) if pos else {"line": None, "text": ""}
        ex._ok("take_profit", [int(x[0]) for x in m_tp[:3]],
               loc["line"], loc["text"], tier="custom")
        if len(m_tp) < 3:
            ex._fail("take_profit 档位数不足 3", f"只找到 {len(m_tp)} 档")
    else:
        ex._fail("take_profit", "未匹配到任何「+N% → 卖25%」档位")
        ex._ok("take_profit", DEFAULTS["take_profit"], None, "（未命中，用 builtin）", "builtin")

    # ── ④ 四层配比（09-01 修复：原正则误匹配波动率 2%）──
    four = dict(DEFAULTS["four_layer"])
    for k, pat in (("bedrock_pct", r"压舱石[^\n]{0,40}?权重\s*([0-9]+)\s*%"),
                   ("sat_pct", r"卫星[^\n]{0,40}?权重\s*([0-9]+)\s*%"),
                   ("cash_pct", r"现金[^\n]{0,40}?权重\s*([0-9]+)\s*%")):
        m = re.search(pat, text)
        if m:
            four[k] = int(m.group(1))
        else:
            ex._fail(f"four_layer.{k}", "未匹配到「权重 NN%」句式")
    m = re.search(r"核心[^\n]{0,40}?权重\s*([0-9]+)\s*%", text)
    if m:
        four["core_min_pct"] = four["core_max_pct"] = int(m.group(1))
    else:
        ex._fail("four_layer.core", "未匹配到「核心…权重 NN%」句式")
    # 合理性：四层权重之和须为 100（v4.5.17 新增 —— 本键此前无任何校验）
    _sum = (four["bedrock_pct"] + four["core_min_pct"] + four["sat_pct"] + four["cash_pct"])
    if _sum != 100:
        ex._fail("four_layer", f"🔴 四层权重之和 = {_sum}% ≠ 100% ⇒ 配置不自洽")
    ex._ok("four_layer", four, None, f"sum={_sum}%", "custom")

    # ── ⑤ 4.3 集中度上限（单只 压舱石/核心/卫星；表格行是权威定义）──
    caps = dict(DEFAULTS["single_position_caps"])
    lo_c, hi_c = rule_keys.STRUCTURED_RANGES["single_position_caps"]
    for layer in ("压舱石", "核心", "卫星"):
        pat = rf"{rule_keys.LINE_START}\|[ \t]*单只{layer}[ \t]*\|[ \t]*≤?\s*¥?\s*([\d,，]+)"
        m = re.search(pat, text, re.MULTILINE)
        tier = "anchored"
        if not m:   # 兜底（表格被改写时的旧路径）
            m = re.search(rf"单只{layer}[^\n]{{0,16}}?¥?\s*([\d,，]+)", text)
            tier = "fallback"
        if m:
            v = int(m.group(1).replace(",", "").replace("，", ""))
            loc = _dict_loc(text, m.start())
            _k = f"single_position_caps.{layer}"
            if not (lo_c <= v <= hi_c):
                ex.rejected[_k] = {"value": v, "range": [lo_c, hi_c], **loc}
                ex._fail(_k, f"🔴 抽取值 {v} 越界 [{lo_c}, {hi_c}] ⇒ 拒收，用 builtin "
                             f"{DEFAULTS['single_position_caps'][layer]}")
            else:
                caps[layer] = v
                ex.sources[_k] = {"line": loc["line"], "text": loc["text"], "tier": tier}
        else:
            ex._fail(f"single_position_caps.{layer}", "未匹配到「单只<层>」上限")
    ex.rules["single_position_caps"] = caps

    # ── ⑥ 板块上限 ──
    spec = rule_keys.SCALAR_KEYS["sector_cap"]
    ex.grab_spec("sector_cap", spec)

    # ── ⑦ MA5 口径 ＋ A2 前日涨幅判据源（v4.5.2 · 用户裁决）──
    m = re.search(r"当日\s*MA5」＝\*\*([^*]{0,12})\*\*", text)
    if m:
        loc = _dict_loc(text, m.start())
        ex._ok("watchlist_confirm_ma_includes_today", ("不含当日" not in m.group(1)),
               loc["line"], loc["text"], tier="custom")
    else:
        ex._fail("watchlist_confirm_ma_includes_today", "未匹配到「当日 MA5」＝**…**」口径句")
        ex._ok("watchlist_confirm_ma_includes_today",
               DEFAULTS["watchlist_confirm_ma_includes_today"], None, "（未命中）", "builtin")

    m = re.search(r"自建日序列缓存[^\n]{0,40}?`([\w.]+\.json)`", text)
    if m:
        loc = _dict_loc(text, m.start())
        ex._ok("a2_prev_day_cache", m.group(1), loc["line"], loc["text"], tier="custom")
    else:
        ex._fail("a2_prev_day_cache", "未匹配到「自建日序列缓存 … `<file>.json`」")
        ex._ok("a2_prev_day_cache", DEFAULTS["a2_prev_day_cache"], None, "（未命中）", "builtin")

    return ex.rules, ex.warns, ex.sources, ex.rejected, ex.warn_details


def _dict_loc(text: str, start: int) -> dict:
    line, snippet = _loc(text, start)
    return {"line": line, "text": snippet}


def extract(text: str):
    """**向后兼容签名**（既有测试与消费方依赖）：返回 `(rules, warns)`。

    需要来源留痕请用 `extract_full()` —— ⛔ 不得改变本函数的返回元数。
    """
    rules, warns, _s, _r, _d = extract_full(text)
    return rules, warns


def main() -> None:
    parser = argparse.ArgumentParser(description="提取规则契约")
    parser.add_argument("--manual", default=None)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "AI-Collab" / "rule_contract.json"))
    args = parser.parse_args()

    manual = Path(args.manual) if args.manual else latest_manual()
    text = manual.read_text(encoding="utf-8")
    rules, warns, sources, rejected, warn_details = extract_full(text)

    version_match = re.search(r"v(\d+(?:\.\d+)?)", manual.name)
    version = f"v{version_match.group(1)}" if version_match else "v?.?"

    contract = {
        "rule_version": version,
        "updated_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": str(manual),
        "rules": rules,
        "warns": warns,
        # v4.5.17 新增三段（**提取健康度的可审计面**）：
        #   sources         每个键取自手册第几行、原文是什么、锚定命中还是兜底命中
        #   sanity_rejected 被合理性区间拒收的值（**空 = 没抓到坏值**，不是「没检查」）
        #   warn_details    每个 warns 键的**原因**（warns 本身仍是裸键名，旧契约不变）
        "sources": sources,
        "sanity_rejected": rejected,
        "warn_details": warn_details,
    }
    # 09-01 修复：保留既有 data 字段（data_date/total_assets/updated/note），
    # 防止 relay 因数据 hash 未变而跳过分发时契约缺数据段
    out = Path(args.out)
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
            for k in ("data_date", "total_assets", "updated", "note"):
                if k in old:
                    contract[k] = old[k]
        except Exception:
            pass
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[rules] contract written: {out}")
    # 🔴 2026-09-18 修正：原为 `len(rules) - 1`，**比实际落盘键数少 1**（实测 33 键报成 32）
    #    `rules` 里没有任何非规则键（逐键核过），那个 `-1` 是**没有依据的**。
    #    属「转述层与定义层无绑定」的同族：脚本**自报的数**与**它刚写进产物的数**对不上，
    #    而自报数是人唯一会看到的东西。
    print(f"[rules] version={version} extracted={len(rules)} keys")
    print(f"[rules] 来源留痕 sources={len(sources)} 键（含手册行号）")
    if rejected:
        print(f"[rules] 🔴 合理性区间拒收 {len(rejected)} 项（已回退 builtin）: "
              f"{', '.join(rejected)}")
    if warns:
        print(f"[rules] WARN 提取失败（使用默认值）: {', '.join(warns)}")
        for k in warns:
            if k in warn_details:
                print(f"        · {k}: {warn_details[k]}")


if __name__ == "__main__":
    main()
