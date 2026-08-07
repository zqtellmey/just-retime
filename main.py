import os
import time
import requests
import pyautogui
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
    """专门在弹出的 DIV 内部定位并执行 3 次 Turnstile 验证穿透"""
    print(f"[INFO] ({step_name}) 开始寻找弹窗 DIV (#turnstile-timer-reset) 内部的人机验证...")

    # 1. 尝试直接调用 SB 内置穿透函数
    try:
        sb.uc_gui_click_captcha()
        time.sleep(1)
    except Exception:
        pass

    # 2. 从 DOM 中精确获取弹出 DIV 的视口坐标，直接定位 DIV 内部的人机勾选框
    try:
        rect = sb.execute_script("""
            const el = document.getElementById('turnstile-timer-reset');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {
                left: r.left,
                top: r.top,
                width: r.width,
                height: r.height
            };
        """)

        if rect:
            # 算出 DIV 内部 CF 人机勾选框的准确坐标
            target_x = int(rect['left'] + 35)
            target_y = int(rect['top'] + (rect['height'] / 2))
            
            print(f"[INFO] ({step_name}) 成功定位弹窗 DIV！内部 CF 验证框坐标: ({target_x}, {target_y})")

            # 在弹窗 DIV 内部的目标点执行 3 次点击，每次间隔 2 秒
            for i in range(3):
                print(f"[INFO] ({step_name}) 正在对弹窗 DIV 内部人机框执行第 {i+1}/3 次点击...")
                pyautogui.click(target_x, target_y)
                time.sleep(2)
        else:
            print(f"[WARN] ({step_name}) 页面中未找到 #turnstile-timer-reset 弹窗 DIV 节点。")

    except Exception as e:
        print(f"[ERROR] ({step_name}) 弹窗 DIV 内部人机穿透异常: {e}")

    print(f"[INFO] ({step_name}) 弹窗 DIV 内部人机验证处理结束。")

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
            try:
                sb.uc_gui_click_captcha()
            except:
                pass
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

            # 1. 在弹出的 DIV 内部处理 CF 人机验证
            handle_cloudflare_in_popup(sb, "Reset弹窗DIV")

            # 留出时间等待人机打勾及解锁按钮
            time.sleep(4)

            # 2. 直接使用 DOM 查找并点击弹窗内的 Just Reset 按钮
            just_reset_xpath = '//button[contains(normalize-space(.), "Just Reset")]'
            
            print("[INFO] 正在寻找弹窗 DIV 内部的 Just Reset 按钮...")
            try:
                sb.wait_for_element(just_reset_xpath, timeout=10)
                print("[INFO] 成功在 DOM 中定位到 Just Reset 按钮，执行点击！")
                sb.click(just_reset_xpath)
            except Exception as e:
                print(f"[WARN] DOM 定位 Just Reset 按钮失败，尝试 JS 强行触发点击: {e}")
                # 备用机制：如果标准 Selenium 点击有弹窗遮罩阻挡，直接执行 JS 点击
                sb.execute_script("""
                    const btns = Array.from(document.querySelectorAll('button'));
                    const targetBtn = btns.find(b => b.textContent.includes('Just Reset'));
                    if (targetBtn) targetBtn.click();
                """)

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
                print("[INFO] 未发现 Start 按钮或当前无需点击。")

            # 截图并发送 Telegram
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
