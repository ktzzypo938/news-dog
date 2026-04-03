"""
爬蟲實務分析腳本
- 每個來源抽樣 5 篇文章
- 分析：URL 分類分布、欄位完整率、文字長度、時間格式、數量差異
"""
import sys
import re
import time
from collections import defaultdict
from datetime import datetime

import base
import sources.cna as cna
import sources.cti as cti
import sources.ltn as ltn
import sources.set as set_
import sources.udn as udn

SOURCES = [
    ('CNA', '中央通訊社', cna,  True),
    ('CTI', '中天新聞',   cti,  False),
    ('LTN', '自由時報',   ltn,  True),
    ('SET', '三立新聞',   set_, True),
    ('UDN', '聯合新聞網', udn,  True),
]

SAMPLE_SIZE = 5
SEP = '─' * 64

def analyze_source(code, name, mod, ssl_verify):
    session = base.create_session(ssl_verify=ssl_verify)
    if not ssl_verify:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    result = {
        'code': code, 'name': name,
        'url_count': 0,
        'url_categories': defaultdict(int),
        'sampled': 0, 'success': 0,
        'fields': defaultdict(int),  # field -> 有值篇數
        'text_lens': [],
        'time_formats': [],
        'issues': [],
    }

    # ── 1. 取 URL 列表 ──
    print(f"\n[{code}] 取得 URL 列表...")
    try:
        urls = list(set(mod.get_list_urls(session)))
    except Exception as e:
        result['issues'].append(f"get_list_urls 失敗: {e}")
        return result

    result['url_count'] = len(urls)

    # 分析 URL 分類分布
    for u in urls:
        cat = _extract_url_category(code, u)
        result['url_categories'][cat] += 1

    # ── 2. 抽樣 5 篇文章 ──
    sample_urls = urls[:SAMPLE_SIZE]
    print(f"[{code}] 共 {len(urls)} 筆 URL，抽樣 {len(sample_urls)} 篇...")

    for i, url in enumerate(sample_urls):
        result['sampled'] += 1
        try:
            article = mod.scrape_article(session, url)
        except Exception as e:
            result['issues'].append(f"scrape_article 例外 ({url}): {e}")
            continue

        if article is None:
            result['issues'].append(f"回傳 None（分類過濾或解析失敗）: {url}")
            continue

        result['success'] += 1

        # 欄位完整度
        for field in ['title', 'cleanText', 'publishedAt', 'imageUrl', 'imagePhotographer']:
            if article.get(field):
                result['fields'][field] += 1

        # 文字長度
        text = article.get('cleanText', '')
        result['text_lens'].append(len(text))

        # 時間格式檢查
        pt = article.get('publishedAt', '')
        result['time_formats'].append(pt)

        # 即時顯示進度
        title_short = (article.get('title') or '')[:40]
        print(f"  [{i+1}] ✅ {title_short}")
        time.sleep(0.2)  # 避免對目標網站造成太大壓力

    return result


def _extract_url_category(code, url):
    """從 URL 推斷文章分類"""
    if code == 'CNA':
        m = re.search(r'/news/([a-z]+)/', url)
        MAP = {'aipl': '政治', 'asoc': '社會', 'aopl': '國際', 'acn': '兩岸'}
        return MAP.get(m.group(1), m.group(1)) if m else '未知'
    if code == 'CTI':
        return 'homepage（無分類）'
    if code == 'LTN':
        m = re.search(r'breakingnews/([a-z]+)', url)
        MAP = {'politics': '政治', 'society': '社會', 'world': '國際'}
        return MAP.get(m.group(1), m.group(1)) if m else '未知'
    if code == 'SET':
        m = re.search(r'NewsID=(\d+)', url)
        return 'NewsID' if m else '未知'
    if code == 'UDN':
        m = re.search(r'breaknews/1/(\d+)', url)
        MAP = {'1': '要聞/政治', '2': '社會', '5': '國際'}
        # UDN story URL 無法直接判斷分類，用 story path
        if '/news/story/' in url:
            return 'story（已規範化）'
        return MAP.get(m.group(1), '未知') if m else '未知'
    return '未知'


def print_report(results):
    print(f"\n{'='*64}")
    print("  實務分析報告")
    print(f"{'='*64}")

    url_counts = {r['code']: r['url_count'] for r in results}
    avg_count = sum(url_counts.values()) / len(url_counts)

    for r in results:
        code = r['code']
        name = r['name']
        count = r['url_count']
        diff = count - avg_count
        diff_str = f"(+{diff:.0f})" if diff > 0 else f"({diff:.0f})"

        print(f"\n{SEP}")
        print(f"  {code} {name}  │  URL 數量: {count} {diff_str}  │  平均: {avg_count:.0f}")
        print(SEP)

        # URL 分類分布
        print("  📂 分類分布:")
        for cat, cnt in sorted(r['url_categories'].items(), key=lambda x: -x[1]):
            bar = '█' * min(cnt, 30)
            print(f"     {cat:<14} {cnt:>3}  {bar}")

        # 欄位完整度
        s = r['success']
        if s > 0:
            print(f"\n  📋 欄位完整度（共 {s}/{r['sampled']} 篇成功）:")
            fields_order = ['title', 'cleanText', 'publishedAt', 'imageUrl', 'imagePhotographer']
            labels = {'title': '標題', 'cleanText': '內文', 'publishedAt': '時間',
                      'imageUrl': '圖片URL', 'imagePhotographer': '攝影師'}
            for f in fields_order:
                cnt = r['fields'].get(f, 0)
                pct = cnt / s * 100
                mark = '✅' if pct >= 80 else ('⚠️ ' if pct >= 40 else '❌')
                required = '（必填）' if f in ('title', 'cleanText', 'publishedAt') else '（選填）'
                print(f"     {mark} {labels[f]:<8} {cnt}/{s}  {pct:.0f}%  {required}")

        # 文字長度
        if r['text_lens']:
            avg_len = sum(r['text_lens']) / len(r['text_lens'])
            min_len = min(r['text_lens'])
            max_len = max(r['text_lens'])
            print(f"\n  📝 內文字元數: 平均 {avg_len:.0f}  最短 {min_len}  最長 {max_len}")
            if min_len < 50:
                print(f"     ⚠️  有文章內文過短（< 50 字），可能選擇器未命中")

        # 時間樣本
        if r['time_formats']:
            print(f"\n  🕐 時間格式樣本:")
            for t in r['time_formats'][:3]:
                print(f"     {t}")

        # 問題
        if r['issues']:
            print(f"\n  ⚠️  發現問題:")
            for issue in r['issues']:
                print(f"     • {issue}")

    # ── 總結比較 ──
    print(f"\n{'='*64}")
    print("  數量差異比較")
    print(f"{'='*64}")
    sorted_counts = sorted(url_counts.items(), key=lambda x: -x[1])
    max_count = sorted_counts[0][1]
    for code, cnt in sorted_counts:
        bar = '█' * int(cnt / max_count * 30)
        flag = '  ← ⚠️  偏少' if cnt < avg_count * 0.5 else ''
        print(f"  {code}  {cnt:>3}  {bar}{flag}")
    print(f"  {'平均':>4}  {avg_count:>3.0f}")


if __name__ == '__main__':
    all_results = []
    for args in SOURCES:
        try:
            r = analyze_source(*args)
            all_results.append(r)
        except Exception as e:
            print(f"\n❌ [{args[0]}] 未預期錯誤: {e}")

    print_report(all_results)
