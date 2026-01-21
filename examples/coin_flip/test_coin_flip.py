from playwright.sync_api import Page, expect


def test_coin_flip(page: Page):
    """Flip 10 Polish 5 Złoty coins on random.org."""

    page.goto("https://www.random.org/")
    try:
        page.get_by_role("button", name="Allow Selected").click(timeout=5000)
    except:  # noqa: E722
        pass

    page.get_by_role("link", name="Games", exact=True).hover()

    page.get_by_role("link", name="Coin Flipper").first.click()

    expect(page.locator("h2")).to_contain_text("Coin Flipper")

    page.locator("select[name=\"num\"]").select_option("10")

    page.locator("select[name=\"cur\"]").select_option(label="Polish 5 Złoty")

    page.get_by_role("button", name="Flip Coin(s)").first.click()
    "Flip the coins"

    expect(page.locator("body")).to_contain_text("You flipped 10 coins")
