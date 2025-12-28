"""Playwright test for Open Mercato application - Complete Quote Creation Flow.

This test demonstrates the complete workflow of creating a quote including:
1. Navigating to sales documents
2. Creating a new quote
3. Selecting customer and sales channel
4. Adding items to the quote
5. Finishing the quote
"""

from playwright.sync_api import Page, expect


def test_open_mercato_complete_quote_creation_flow(page: Page) -> None:
    """Test the complete flow of creating, populating, and finishing a quote in Open Mercato."""
    
    # ============================================================================
    # PART 1: LOGIN
    # ============================================================================
    page.goto("http://localhost:3000/login?role=admin")
    page.wait_for_selector("#email")
    
    page.fill("#email", "admin@acme.com")
    page.fill("#password", "secret")
    
    sign_in_button_xpath = "/html/body/div[2]/div[1]/div/div/div[2]/form/button"
    page.locator(f"xpath={sign_in_button_xpath}").click()
 
    
    page.wait_for_timeout(700)
    # ============================================================================
    # PART 2: NAVIGATE TO Quote
    # ============================================================================
    quotes_xpath = "/html/body/div[2]/div[1]/div/aside/div/div[2]/nav/div[3]/div[1]/a[3]"
    page.locator(f"xpath={quotes_xpath}").click()
   
    click_create_sales_document_xpath = "/html/body/div[2]/div[1]/div/div/main/div/div/div/div[1]/div[1]/div[2]/a"
    page.locator(f"xpath={click_create_sales_document_xpath}").click()

    # ============================================================================
    # PART 3: GENERATE ID FOR NEW QUOTE
    # ============================================================================
    generate_id_xpath = "/html/body/div[2]/div[1]/div/div/main/div/div/div/div[2]/form/div[1]/div[1]/div[1]/div/div/div[2]/div/div/button"
    page.locator(f"xpath={generate_id_xpath}").click()

    # ============================================================================
    # PART 4: SELECT CUSTOMER
    # ============================================================================
    customer_dropdown_xpath = "/html/body/div[2]/div[1]/div/div/main/div/div/div/div[2]/form/div[1]/div[1]/div[2]/div[1]/div/div[1]/div/div/div[1]/input"
    page.locator(f"xpath={customer_dropdown_xpath}").fill("Test")

    select_first_customer_xpath = "/html/body/div[2]/div[1]/div/div/main/div/div/div/div[2]/form/div[1]/div[1]/div[2]/div[1]/div/div[1]/div/div[2]/div/div[1]"
    page.locator(f"xpath={select_first_customer_xpath}").click()

    # ============================================================================
    # PART 5: INPUT CUSTOMER EMAIL
    # ============================================================================
    customer_email_xpath = "/html/body/div[2]/div[1]/div/div/main/div/div/div/div[2]/form/div[1]/div[1]/div[2]/div[1]/div/div[2]/div/input"
    page.locator(f"xpath={customer_email_xpath}").fill("john.smith@test.com")

    # ============================================================================
    # PART 6: SELECT SALES CHANNEL
    # ============================================================================
    sales_channel_input_xpath = "/html/body/div[2]/div[1]/div/div/main/div/div/div/div[2]/form/div[1]/div[1]/div[3]/div/div/div[1]/div/div[1]/div/input"
    page.locator(f"xpath={sales_channel_input_xpath}").fill("Online")

    select_sales_channel_xpath = "/html/body/div[2]/div[1]/div/div/main/div/div/div/div[2]/form/div[1]/div[1]/div[3]/div/div/div[1]/div/div[2]/div/div[2]/div[2]/div[2]/button"
    page.locator(f"xpath={select_sales_channel_xpath}").click()
    page.wait_for_timeout(1000)
    #Create Quote Final Button
    click_create_button_at_the_top = "/html/body/div[2]/div[1]/div/div/main/div/div/div/div[2]/form/div[2]/div[2]/button"
    page.locator(f"xpath={click_create_button_at_the_top}").click()
    page.wait_for_timeout(700)
    # ============================================================================
    click_items_tab = "/html/body/div[2]/div[1]/div/div/main/div/div/div[4]/div[1]/div/button[3]"
    page.locator(f"xpath={click_items_tab}").click()
    click_add_item_button = "/html/body/div[2]/div[1]/div/div/main/div/div/div[4]/div[2]/div/button"
    page.locator(f"xpath={click_add_item_button}").click() # <hint>Say click add item button</hint>
    # Click "Add item" button
    page.wait_for_timeout(700)

    
    # Wait for the modal to appear
    # page.wait_for_selector("text=Add line", timeout=5000)
    
    # Fill in the product search field
    page.locator('input[placeholder="Search product"]').fill("Atlas")
    
    # Wait for search results and click the first result
    page.wait_for_timeout(500)  # Small delay for search results

    page.get_by_text("Atlas Runner Sneaker").locator("..").click()      # parent

    variant_xpath = "/html/body/div[6]/div[2]/div/form/div[1]/div[1]/div/div/div/div[3]/div/div[2]/div/div[1]"
    page.locator(f"xpath={variant_xpath}").click() 
    
    # # Set price to 138
    price_xpath = "/html/body/div[6]/div[2]/div/form/div[1]/div[1]/div/div/div/div[5]/div/input"
    page.locator(f"xpath={price_xpath}").fill("138")
    page.wait_for_timeout(500)
    # # Select "Pending" status
    page.locator('input[placeholder="Select status"]').fill("pending") 
    
    
    # Click "Pending" option
    page.get_by_text("Pending").locator("..").click()      
    # Click the "Add item" button to confirm
    page.locator("//button[contains(text(), 'Add item')]").click()
    # close_window_xpath = "/html/body/div[14]/button"
    # page.locator(f"xpath={close_window_xpath}").click()
    final_price = "/html/body/div[2]/div[1]/div/div/main/div[2]/div/div[5]/div/table/tfoot/tr[1]/td[2]/span"

    expect(page.locator(f"xpath={final_price}")).to_contain_text("$112.20")


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        page = browser.new_page()

        try:
            test_open_mercato_complete_quote_creation_flow(page)
        finally:
            browser.close()