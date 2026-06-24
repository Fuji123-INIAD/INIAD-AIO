"""Open the persistent MOOCs profile for a user-controlled manual login."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT_DIR / "data" / "probe" / "moocs_profile"
SIGNIN_URL = "https://moocs.iniad.org/signin"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as error:
        raise RuntimeError("Playwright is not installed in this Python environment") from error

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(SIGNIN_URL, wait_until="domcontentloaded", timeout=30000)
            except PlaywrightTimeoutError:
                print("サインインページの読み込みがタイムアウトしました。ブラウザ画面を確認してください。")

            print("ブラウザ上でINIAD MOOCsへ手動ログインしてください。")
            print("このスクリプトは入力や送信を自動操作しません。")
            input("ログインが完了したら、ここで Enter を押してブラウザを閉じてください: ")
        except (EOFError, KeyboardInterrupt):
            print("\n入力待ちを終了し、ブラウザを閉じます。")
        finally:
            context.close()


if __name__ == "__main__":
    main()
