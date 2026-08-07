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

def debug_check_elements(sb):
    """预先查找页面上的关键元素并输出结果，辅助排查"""
    print("=" * 40)
    print("[DEBUG] 开始检查页面元素定位状态：")
    
    selectors = {
        "Cookie 按钮 (button.cky-btn-accept)": "button.cky-btn-accept",
        "邮箱输入框 (input[name='Email'])": "input[name='Email']",
        "密码输入框 (//*[@id='password'])": "//*[@id='password']",
        "密码输入框备用 (input[name='Password'])": "input[name='Password']",
        "提交按钮 (button[type='submit'])": "button[type='submit']",
        "CF 响应 Token 隐藏框 (input[name='cf-turnstile-response'])": "input[name='cf-turnstile-response']"
    }
    
    for name, selector in selectors.items():
        try:
            elem = sb.find_element(selector, timeout=2)
            if elem:
                print(f"  [√] {name} -> 查找成功")
        except Exception:
            print(f"  [×] {name} -> 未找到")
            
    print("=" * 40)

def click_at_coordinates_with_red_dot(sb, x, y):
    """在指定坐标执行点击，并在页面上生成一个醒目的红色圆点标记用于定位校准"""
    print(f"[INFO] 正在执行坐标点击 -> X: {x}, Y: {y}")
    
    # 注入红点并直接通过坐标触发点击事件，不依赖任何外部 ActionChains
    js_code = f"""
    (function() {{
        // 1. 创建红点元素
        var dot = document.createElement('div');
        dot.style.position = 'fixed';
        dot.style.left = '{x}px';
        dot.style.top = '{y}px';
        dot.style.width = '16px';
        dot.style.height = '16px';
        dot.style.backgroundColor = 'red';
        dot.style.borderRadius = '50%';
        dot.style.border = '2px solid white';
        dot.style.boxShadow = '0 0 10px black';
        dot.style.zIndex = '999999';
        dot.style.transform = 'translate(-50%, -50%)';
        document.body.appendChild(dot);

        // 2. 获取该坐标下的顶层元素并点击
        var targetElem = document.elementFromPoint({x}, {y});
        if (targetElem) {{
            targetElem.click();
            console.log("成功点击元素: ", targetElem);
        }} else {{
            console.log("未找到坐标对应的元素");
        }}
    }})();
    """
    try:
        sb.driver.execute_script(js_code)
    except Exception as e:
        print(f"[WARN] 坐标 JS 点击异常: {e}")

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

            # 点击 Reset timer 按钮
            print("[INFO] 正在点击 Reset timer...")
            sb.wait_for_element('button[aria-label="Reset timer"]', timeout=15)
            sb.click('button[aria-label="Reset timer"]')
            time.sleep(3)

            # 处理可能再次出现的验证
            handle_cloudflare_turnstile(sb, "Reset弹窗")

            # ==================== 使用坐标点击 Just Reset 按钮（带红点提示） ====================
            print("[INFO] 准备通过坐标点击弹窗中的 Just Reset 按钮...")
            
            # 初始设定的坐标位置（可根据运行后的截图红点位置调整）
            TARGET_X = 590
            TARGET_Y = 795
            
            click_at_coordinates_with_red_dot(sb, TARGET_X, TARGET_Y)
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
