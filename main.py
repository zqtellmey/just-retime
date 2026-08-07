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
    """固定执行 3 次物理点击，每次间隔 2 秒，不判断成败直接执行后续动作"""
    print(f"[INFO] ({step_name}) 开始执行 Cloudflare Turnstile 穿透（固定尝试 3 次，间隔 2 秒）...")

    for cf_attempt in range(3):
        try:
            print(f"[INFO] ({step_name}) 尝试物理 GUI 点击验证 (第 {cf_attempt + 1}/3 次)...")
            sb.uc_gui_click_captcha()
        except Exception as e:
            print(f"[WARN] ({step_name}) 第 {cf_attempt + 1} 次点击异常: {e}")
        
        print(f"[INFO] ({step_name}) 等待 2 秒...")
        time.sleep(2)
        
    print(f"[INFO] ({step_name}) 3 次固定点击完成，继续执行后续动作。")
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

def test_draw_center_red_dot(sb):
    """动态获取窗口尺寸并在正中心画一个强力高亮红点（固定在屏幕中央）"""
    js_code = """
    (() => {
        // 1. 获取当前浏览器视口中心坐标
        const centerX = window.innerWidth / 2;
        const centerY = window.innerHeight / 2;
        
        // 2. 创建固定定位的红点，确保不受页面滚动影响
        const marker = document.createElement('div');
        marker.id = 'center-test-marker';
        marker.style.position = 'fixed';
        marker.style.left = centerX + 'px';
        marker.style.top = centerY + 'px';
        marker.style.width = '30px';
        marker.style.height = '30px';
        marker.style.backgroundColor = 'red';
        marker.style.borderRadius = '50%';
        marker.style.border = '3px solid yellow';
        marker.style.boxShadow = '0 0 15px red, 0 0 5px black';
        marker.style.zIndex = '2147483647'; // 设为 32 位整型最大值，盖过所有 Modal 弹窗
        marker.style.transform = 'translate(-50%, -50%)';
        marker.style.pointerEvents = 'none'; // 避免挡住真实点击
        
        document.body.appendChild(marker);
        
        return {
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            centerX: centerX,
            centerY: centerY
        };
    })();
    """
    try:
        res = sb.execute_script(js_code)
        print(f"[INFO] 视口分辨率: {res['innerWidth']}x{res['innerHeight']}，红点已成功绘制在正中心: ({res['centerX']}, {res['centerY']})")
        return res['centerX'], res['centerY']
    except Exception as e:
        print(f"[ERROR] 正中心红点绘制失败: {e}")
        return None, None

def main():
    if not USER_EMAIL or not FIXED_PASSWORD or not LOGIN_URL or not TARGET_URL:
        print("[ERROR] 缺少必要的环境变量（USER_EMAIL, FIXED_PASSWORD, LOGIN_URL, TARGET_URL），请检查配置。")
        return

    # 使用 SeleniumBase uc 模式启动浏览器，显式锁定 1920x1080 窗口以防尺寸异常
    with SB(uc=True, test=True, locale="zh") as sb:
        screenshot_path = "step_screenshot.png"
        
        try:
            # 强制设定浏览器窗口尺寸，便于稳定观察
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
            
            handle_cloudflare_turnstile(sb, "登录页")

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
            time.sleep(3)

            handle_cloudflare_turnstile(sb, "Reset弹窗")

            # ==================== 测试：在屏幕正中间绘制红点 ====================
            print("[INFO] 准备在屏幕正中心测试绘制红点...")
            center_x, center_y = test_draw_center_red_dot(sb)
            
            if center_x and center_y:
                # 尝试用物理鼠标点击中心点，验证坐标系统
                try:
                    import pyautogui
                    pyautogui.click(center_x, center_y)
                    print(f"[INFO] 已尝试点击中心红点坐标 ({center_x}, {center_y})。")
                except Exception as e:
                    print(f"[WARN] 物理点击中心红点异常: {e}")

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

            # 截取带有屏幕正中央红点的截图发往 Telegram
            sb.save_screenshot(screenshot_path)
            msg = (
                f"【测试步骤】正中心红点测试完成！\n"
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
