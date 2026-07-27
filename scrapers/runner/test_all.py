"""
爬蟲逐一測試腳本
測試每個來源：
  1. get_list_urls 能不能取到 URL
  2. scrape_article 第一筆 URL 能不能正確解析 title / cleanText / publishedAt / imageUrl
"""
import sys

import base

SEP = '=' * 60

def check(label, value, show=True):
    ok = bool(value)
    mark = '✅' if ok else '❌'
    display = str(value)[:80] if show else '(略)'
    print(f"  {mark} {label}: {display}")
    return ok

def test_source(code, name, mod, ssl_verify):
    print(f"\n{SEP}")
    print(f"  [{code}] {name}")
    print(SEP)

    session = base.create_session(ssl_verify=ssl_verify)
    if not ssl_verify:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # ── 1. 取得文章列表 URL ──
    print("\n[1] get_list_urls")
    try:
        urls = mod.get_list_urls(session)
    except Exception as e:
        print(f"  ❌ 例外: {e}")
        return False

    ok_urls = check(f"取到 URL 數量: {len(urls)}", urls)
    if not ok_urls:
        print("  ↳ 無法繼續（沒有 URL）")
        return False

    # 顯示前 3 筆 URL
    unique_urls = list(dict.fromkeys(urls))
    for i, u in enumerate(unique_urls[:3]):
        print(f"     [{i+1}] {u}")

    # ── 2. 爬取第一筆文章 ──
    print("\n[2] scrape_article（第一筆 URL）")
    test_url = unique_urls[0]
    print(f"  URL: {test_url}")

    try:
        article = mod.scrape_article(session, test_url)
    except Exception as e:
        print(f"  ❌ 例外: {e}")
        return False

    if article is None:
        print("  ❌ scrape_article 回傳 None（可能被分類過濾或解析失敗）")
        # 對 CTI 可能因分類過濾，多試幾筆
        if code == 'CTI':
            print("  → CTI 特殊：嘗試後 5 筆 URL 找符合分類的文章...")
            for u in unique_urls[1:6]:
                print(f"    試: {u}")
                try:
                    article = mod.scrape_article(session, u)
                    if article:
                        print(f"    ✅ 第 {unique_urls.index(u)+1} 筆成功")
                        break
                except Exception:
                    pass
        if article is None:
            return False

    ok = True
    ok &= check("title",       article.get('title'))
    ok &= check("cleanText",   article.get('cleanText', '')[:80], show=True)
    ok &= check("publishedAt", article.get('publishedAt'))
    check("imageUrl",      article.get('imageUrl', ''), show=True)      # 非必填，只顯示
    check("photographer",  article.get('imagePhotographer', '-'), show=True)  # 非必填

    if not ok:
        print("\n  ⚠️  必填欄位有缺漏，此爬蟲可能需要調整選擇器")

    return ok


if __name__ == '__main__':
    results = {}
    for args in base.iter_enabled_sources():
        try:
            results[args[0]] = test_source(*args)
        except Exception as e:
            print(f"\n❌ [{args[0]}] 發生未預期錯誤: {e}")
            results[args[0]] = False

    print(f"\n{SEP}")
    print("  總結")
    print(SEP)
    all_ok = True
    for code, ok in results.items():
        mark = '✅' if ok else '❌'
        print(f"  {mark} {code}")
        if not ok:
            all_ok = False

    print()
    sys.exit(0 if all_ok else 1)
