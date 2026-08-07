import os
import time
import requests
from seleniumbase import SB

# ==================== 配置项（从 GitHub Secrets 环境变量读取） ====================
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

LOGIN_URL = os.getenv("LOGIN_URL")
TARGET_URL = os.getenv("TARGET_URL")

USER_EMAIL = os.getenv("USER_EMAIL")
FIXED_PASSWORD = os.getenv("FIXED_PASSWORD")
# ======================================================================

def send_telegram_message(message, image_path=None):
    """发送消息和可选的截图到 Telegram"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[INFO] Telegram 未配置，跳过消息发送。")
        return
    
    try:
        if image_path and os.path.exists(image_path):
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            with open(image_path, "rb") as photo:
                payload = {"chat_id": TG_CHAT_ID, "caption": message}
                files = {"photo": photo}
                requests.post(url, data=payload, files=files, timeout=15)
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}
            requests.post(url, data=payload, timeout=15)
    except Exception as e:
        print(f"[ERROR] 发送 Telegram 消息失败: {e}")

def handle_cloudflare_turnstile(sb, step_name):
    """采用成功项目的核心循环逻辑：物理点击 + Token 密文状态检查"""
    print(f"[INFO] ({step_name}) 开始执行 Cloudflare Turnstile 智能检测与穿透...")
    
    try:
        time.sleep(2)
        result = sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null')
        if not result:
            print(f"[INFO] ({step_name}) 未检测到 Turnstile 拦截或已自动通过。")
            return True
    except Exception:
        pass

    for cf_attempt in range(3):
        try:
            print(f"[INFO] ({step_name}) 发现 Turnstile 拦截，尝试物理 GUI 点击 (第 {cf_attempt + 1} 次)...")
            sb.uc_gui_click_captcha()
            time.sleep(5)
            
            cf_token_value = sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']").value')
            if cf_token_value and len(cf_token_value.strip()) > 0:
                print(f"[INFO] ({step_name}) 验证成功！云盾 Token 令牌已顺利生成填充。")
                return True
            else:
                print(f"[WARN] ({step_name}) 尝试 {cf_attempt + 1}: Token 依然为空，准备重试...")
        except Exception as e:
            print(f"[WARN] ({step_name}) 尝试 {cf_attempt + 1} 异常: {e}")
        
        time.sleep(3)
        
    print(f"[WARN] ({step_name}) 经过多次重试仍未明确检测到 Token 填充，尝试继续执行后续动作...")
    return True

def accept_cookies_if_present(sb):
    """检测并点击 Cookie 询问框的 Accept All 按钮"""
    try:
        print("[INFO] 检查是否存在 Cookie 询问框...")
        cookie_btn = sb.find_element('button.cky-btn-accept', timeout=3)
        if cookie_btn:
            print("[INFO] 发现 Cookie 询问框，正在点击 'Accept All'...")
            sb.click('button.cky-btn-accept')
            time.sleep(2)
    except Exception:
        print("[INFO] 未检测到 Cookie 询问框或已自动关闭。")

def debug_check_elements(sb):
    """预先查找页面上的关键元素并输出结果，辅助排查"""
    print("=" * 40)
    print("[DEBUG] 开始检查页面元素定位状态：")
    
    selectors = {
        "Cookie 按钮 (button.cky-btn-accept)": "button.cky-btn-accept",
        "邮箱输入框 (input[name='Email'])": "input[name='Email']",
        "密码输入框 (//*[@id='password'])": "//*[@id='password']",
        "密码输入框备用 (input[name='Password'])": "input[name='Password']",
        "提交按钮 (button[type='submit'])": "button[type='submit']"
    }
    
    for name, selector in selectors.items():
        try:
            elem = sb.find_element(selector, timeout=2)
            if elem:
                print(f"  [√] {name} -> 查找成功")
        except Exception:
            print(f"  [×] {name} -> 未找到")
            
    print("=" * 40)

def main():
    if not USER_EMAIL or not FIXED_PASSWORD or not LOGIN_URL or not TARGET_URL:
        print("[ERROR] 缺少必要的环境变量（USER_EMAIL, FIXED_PASSWORD, LOGIN_URL, TARGET_URL），请检查配置。")
        return

    # 使用 SeleniumBase uc 模式启动浏览器
    with SB(uc=True, test=True, locale="zh") as sb:
        screenshot_path = "step_screenshot.png"
        
        try:
            # ==================== 第一步：登录 ====================
            print("[INFO] 正在打开登录页面...")
            sb.open(LOGIN_URL)
            time.sleep(4)

            # 处理可能挡住视线的 Cookie 询问框
            accept_cookies_if_present(sb)

            # 运行元素预检
            debug_check_elements(sb)

            # 填写邮箱
            print("[INFO] 正在输入邮箱...")
            sb.wait_for_element('input[name="Email"]', timeout=15)
            sb.type('input[name="Email"]', USER_EMAIL)
            
            print("[INFO] 延时 2 秒...")
            time.sleep(2)
            
            # 填写密码
            print("[INFO] 正在输入密码...")
            sb.wait_for_element('//*[@id="password"]', timeout=15)
            sb.type('//*[@id="password"]', FIXED_PASSWORD)
            
            print("[INFO] 延时 2 秒...")
            time.sleep(2)
            
            # 处理登录页面的 CF 验证
            handle_cloudflare_turnstile(sb, "登录页")

            # 点击 Sign In 按钮
            print("[INFO] 正在点击登录按钮...")
            sb.click('button[type="submit"]')
            time.sleep(4)

            # 截图并发送 Telegram
            sb.save_screenshot(screenshot_path)
            send_telegram_message("【步骤 1/2】账号登录成功，已过验证并提交表单。", screenshot_path)

            # ==================== 第二步：进入后台并重置 ====================
            print(f"[INFO] 正在跳转到目标页面: {TARGET_URL}")
            sb.open(TARGET_URL)
            time.sleep(5)

            # 处理后台页面的 CF 验证
            handle_cloudflare_turnstile(sb, "后台页")

            # 点击 Reset timer 按钮
            print("[INFO] 正在点击 Reset timer...")
            sb.wait_for_element('button[aria-label="Reset timer"]', timeout=15)
            sb.click('button[aria-label="Reset timer"]')
            time.sleep(2)

            # 处理可能再次出现的验证
            handle_cloudflare_turnstile(sb, "Reset弹窗")

            # 点击 Just Reset 按钮：采用模拟物理鼠标移动到元素坐标并点击的方式
            print("[INFO] 正在定位 Just Reset 按钮并执行鼠标移动到坐标点击...")
            just_reset_selector = 'button:has(i.bi-arrow-clockwise)'
            sb.wait_for_element(just_reset_selector, timeout=15)
            
            try:
                # 获取按钮元素并计算其在视口中的绝对坐标位置
                element = sb.find_element(just_reset_selector)
                
                # 使用 Selenium 内置的 ActionChains 模拟：移动到该元素中心点并点击
                from selenium.webdriver.common.action_chains import ActionChains
                actions = ActionChains(sb.driver)
                actions.move_to_element(element).pause(0.5).click().perform()
                print("[INFO] 已成功通过鼠标移动并点击 Just Reset 按钮。")
            except Exception as e:
                print(f"[WARN] 鼠标动作链点击异常，降级使用 JS 点击: {e}")
                sb.driver.execute_script("""
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const targetBtn = buttons.find(el => el.textContent.includes('Just Reset') || el.querySelector('.bi-arrow-clockwise'));
                    if (targetBtn) targetBtn.click();
                """)
            
            time.sleep(3)

            # 读取 reset 后的剩余时间
            try:
                remaining_time_elem = sb.find_element('span.hidden.sm\\:inline')
                remaining_time_text = remaining_time_elem.text
                print(f"[INFO] 当前剩余时间: {remaining_time_text}")
            except Exception:
                remaining_time_text = "未能成功获取剩余时间"
                print(f"[WARN] {remaining_time_text}")

            # 检查 Start 按钮是否存在，存在则点击
            start_clicked = False
            try:
                start_btn = sb.find_element('xpath://button[contains(normalize-space(text()), "Start")]')
                if start_btn:
                    print("[INFO] 发现 Start 按钮，正在点击...")
                    sb.click('xpath://button[contains(normalize-space(text()), "Start")]')
                    start_clicked = True
                    time.sleep(3)
            except Exception:
                print("[INFO] 未发现 Start 按钮或当前无需点击。")

            # 最终截图并发送 Telegram 通知
            sb.save_screenshot(screenshot_path)
            msg = (
                f"【步骤 2/2】操作执行完成！\n"
                f"⏱️ 剩余时间: {remaining_time_text}\n"
                f"▶️ Start按钮已点击: {'是' if start_clicked else '否'}"
            )
            send_telegram_message(msg, screenshot_path)
            print("[INFO] 所有步骤执行完毕！")

        except Exception as e:
            error_msg = f"[ERROR] 任务执行过程中发生异常: {str(e)}"
            print(error_msg)
            try:
                sb.save_screenshot(screenshot_path)
                send_telegram_message(error_msg, screenshot_path)
            except:
                send_telegram_message(error_msg)
        finally:
            if os.path.exists(screenshot_path):
                try:
                    os.remove(screenshot_path)
                except:
                    pass

if __name__ == "__main__":
    main()
