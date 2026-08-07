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

def handle_cloudflare_in_popup(sb, step_name):
    """在弹窗内部执行 Turnstile 验证穿透（尝试 3 次）"""
    print(f"[INFO] ({step_name}) 开始处理人机验证...")

    for i in range(3):
        try:
            print(f"[INFO] ({step_name}) 尝试第 {i+1}/3 次人机验证穿透...")
            sb.uc_gui_click_captcha()
        except Exception as e:
            print(f"[WARN] ({step_name}) 第 {i+1} 次验证穿透跳过或未找到: {e}")
        time.sleep(2)

    print(f"[INFO] ({step_name}) 人机验证处理流程完成。")

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

def click_just_reset_button(sb):
    """验证并尝试点击 Just Reset 按钮"""
    print("[INFO] [诊断模式] 开始全面检测页面中是否存在 'Just Reset' 按钮...")

    # 1. 先用 JS 在页面全局深度搜寻该按钮节点
    found_info = sb.execute_script("""
        const btns = Array.from(document.querySelectorAll('button'));
        const target = btns.find(b => b.textContent.includes('Just Reset'));
        if (target) {
            return {
                found: true,
                tagName: target.tagName,
                className: target.className,
                isVisible: target.offsetWidth > 0 && target.offsetHeight > 0,
                text: target.textContent.trim()
            };
        }
        return { found: false };
    """)

    print(f"[INFO] [诊断结果] JS 查询结果: {found_info}")

    # 2. 尝试用 Selenium 标准 XPath 定位并点击
    just_reset_xpath = '//button[contains(normalize-space(.), "Just Reset")]'
    try:
        print("[INFO] 尝试使用 Selenium Standard XPath 定位点击...")
        sb.wait_for_element(just_reset_xpath, timeout=8)
        sb.click(just_reset_xpath)
        print("[SUCCESS] 成功通过 Selenium 定位并点击了 Just Reset 按钮！")
        return True
    except Exception as e:
        print(f"[WARN] Selenium 标准点击失败: {e}")

    # 3. 如果 Selenium 点击失败，但 JS 诊断找到了元素，使用 JS 强制强行点击
    if found_info and found_info.get("found"):
        print("[INFO] 尝试通过 JavaScript 脚本直接触发强行点击 (.click())...")
        clicked = sb.execute_script("""
            const btns = Array.from(document.querySelectorAll('button'));
            const target = btns.find(b => b.textContent.includes('Just Reset'));
            if (target) {
                target.click();
                return true;
            }
            return false;
        """)
        if clicked:
            print("[SUCCESS] 成功通过 JS 强制点击了 Just Reset 按钮！")
            return True

    print("[ERROR] 未能找到或点击 Just Reset 按钮！")
    return False

def main():
    if not USER_EMAIL or not FIXED_PASSWORD or not LOGIN_URL or not TARGET_URL:
        print("[ERROR] 缺少必要的环境变量（USER_EMAIL, FIXED_PASSWORD, LOGIN_URL, TARGET_URL），请检查配置。")
        return

    with SB(uc=True, test=True, locale="zh") as sb:
        screenshot_path = "step_screenshot.png"
        
        try:
            sb.set_window_size(1920, 1080)

            # ==================== 第一步：登录 ====================
            print("[INFO] 正在打开登录页面...")
            sb.open(LOGIN_URL)
            time.sleep(4)

            accept_cookies_if_present(sb)

            print("[INFO] 正在输入邮箱...")
            sb.wait_for_element('input[name="Email"]', timeout=15)
            sb.type('input[name="Email"]', USER_EMAIL)
            time.sleep(2)
            
            print("[INFO] 正在输入密码...")
            sb.wait_for_element('//*[@id="password"]', timeout=15)
            sb.type('//*[@id="password"]', FIXED_PASSWORD)
            time.sleep(2)
            
            # 登录页面的 CF 穿透
            handle_cloudflare_in_popup(sb, "登录页")
            time.sleep(3)

            print("[INFO] 正在点击登录按钮...")
            sb.click('button[type="submit"]')
            time.sleep(4)

            sb.save_screenshot(screenshot_path)
            send_telegram_message("【步骤 1/2】账号登录成功，已过验证并提交表单。", screenshot_path)

            # ==================== 第二步：进入后台并重置 ====================
            print(f"[INFO] 正在跳转到目标页面: {TARGET_URL}")
            sb.open(TARGET_URL)
            time.sleep(5)

            print("[INFO] 正在点击 Reset timer...")
            sb.wait_for_element('button[aria-label="Reset timer"]', timeout=15)
            sb.click('button[aria-label="Reset timer"]')
            
            # 等待 Reset 弹窗完全渲染
            print("[INFO] 等待 Reset 弹窗 DIV 渲染...")
            time.sleep(4)

            # 1. 处理弹窗内的 CF 人机验证
            handle_cloudflare_in_popup(sb, "Reset弹窗DIV")

            # 留出时间等待人机打勾及解锁按钮
            time.sleep(4)

            # 2. 执行诊断及点击 Just Reset 按钮
            reset_success = click_just_reset_button(sb)

            time.sleep(5)

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
                print("[INFO] 未发现 Start 按钮或当前步骤无需点击。")

            # 截图并发送 Telegram
            sb.save_screenshot(screenshot_path)
            msg = (
                f"【步骤 2/2】操作执行完成！\n"
                f"🎯 Just Reset 点击成功: {'是' if reset_success else '否'}\n"
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
