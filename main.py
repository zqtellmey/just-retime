import os
import sys
import time
import requests
from seleniumbase import SB
from PIL import Image, ImageDraw

# ==================== 配置项（从 GitHub Secrets 环境变量读取） ====================
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

LOGIN_URL = os.getenv("LOGIN_URL", "")
TARGET_URL = os.getenv("TARGET_URL", "")

USER_EMAIL = os.getenv("USER_EMAIL", "")
FIXED_PASSWORD = os.getenv("FIXED_PASSWORD", "")
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

def draw_red_dot_on_screenshot(image_path, x, y, radius=10):
    """在指定坐标 (x, y) 处画一个醒目的红点，用于可视化点击位置"""
    try:
        if not os.path.exists(image_path):
            return
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        # 绘制红色实心圆圈（带外发光效果由粗线条代替）
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill="red", outline="white", width=3)
        img.save(image_path)
        print(print(f"[DEBUG] 已在截图坐标 ({x}, {y}) 处绘制红点可视化标记。"))
    except Exception as e:
        print(f"[WARN] 绘制红点失败: {e}")

def handle_cloudflare_turnstile(sb, step_name=""):
    """
    带红点调试的过 CF 人机验证逻辑
    每次准备 GUI 点击前，先捕获当前真实坐标并打上红点发送 Telegram 验证
    """
    prefix = f"({step_name}) " if step_name else ""
    screenshot_path = "step_screenshot.png"
    try:
        time.sleep(2)
        # 1. 探测主页面是否存在 turnstile 响应框
        result = sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null')
        if not result:
            print(f"[INFO] {prefix}未检测到 Turnstile 拦截或已自动通过。")
            return True
        
        print(f"[INFO] {prefix}发现 Turnstile 拦截，准备执行物理 GUI 点击...")

        # 🎯 尝试通过 JS 获取当前 Turnstile 容器的屏幕绝对坐标，用于在图上画红点
        try:
            box_coords = sb.driver.execute_script("""
                const el = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                if (el) {
                    const rect = el.getBoundingClientRect();
                    return {
                        x: Math.round(rect.left + rect.width / 2),
                        y: Math.round(rect.top + rect.height / 2)
                    };
                }
                return null;
            """)
            if box_coords:
                # 截取当前画面并打上红点
                sb.save_screenshot(screenshot_path)
                draw_red_dot_on_screenshot(screenshot_path, box_coords['x'], box_coords['y'])
                send_telegram_message(f"🔴 <b>[点击坐标调试]</b> {step_name} 预判点击位置已用红点标出。", screenshot_path)
        except Exception as coord_err:
            print(f"[DEBUG] 坐标预判失败: {coord_err}")

        # 执行物理 GUI 点击
        sb.uc_gui_click_captcha()
        time.sleep(3)

        # 校验 GUI 点击是否成功注入 Token
        token = sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']")?.value')
        if token and len(token.strip()) > 0:
            print(f"[INFO] {prefix}GUI 点击成功，Token 已注入！")
            return True

        # 2. 精准切入 Turnstile iframe 执行深层点击
        print(f"[INFO] {prefix}GUI 点击未触发 Token，尝试精准切入 iframe 点击复选框...")
        iframes = sb.find_elements('iframe[src*="challenges.cloudflare.com"]')
        for idx, frame in enumerate(iframes):
            try:
                sb.switch_to_frame(frame)
                time.sleep(1)
                
                selectors = ['#challenge-stage', 'input[type="checkbox"]', '.ctp-checkbox-label', 'span.mark', '#cb-i']
                clicked = False
                for target_sel in selectors:
                    if sb.is_element_visible(target_sel):
                        print(f"[INFO] {prefix}在 iframe[{idx}] 内部找到复选框 [{target_sel}]，执行精细点击...")
                        sb.uc_click(target_sel, reconnect_time=2)
                        clicked = True
                        time.sleep(3)
                        break
                
                if not clicked:
                    sb.driver.execute_script('document.querySelector("input, label, span")?.click();')
                    time.sleep(2)

                sb.switch_to_parent_frame()
                
                token_check = sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']")?.value')
                if token_check and len(token_check.strip()) > 0:
                    print(f"[INFO] {prefix}iframe[{idx}] 精准点击成功，Token 已注入！")
                    return True

            except Exception as f_err:
                print(f"[WARN] {prefix}切入 iframe[{idx}] 点击时捕获异常: {f_err}")
                sb.switch_to_default_content()

        sb.switch_to_default_content()
        return True
    except Exception as e:
        print(f"[WARN] {prefix}执行 Turnstile 验证穿透时捕获到异常: {e}")
        sb.switch_to_default_content()
        return False

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
        sys.exit(1)

    opts = {
        "uc": True,                 # 开启反爬穿透
        "test": True,               # 开启测试防护模式
        "locale": "zh",             # 语言偏好
        "headed": False,            # 后台渲染方式
        "timeout_multiplier": 0.5   # 适当提升超时容忍度
    }

    print("🚀 正在初始化 SeleniumBase 环境...")

    try:
        with SB(**opts) as sb:
            sb.driver.set_page_load_timeout(45)
            sb.driver.set_window_size(1920, 1080)
            
            screenshot_path = "step_screenshot.png"

            # ==================== 第一步：登录 ====================
            print(f"[INFO] 正在打开登录页面: {LOGIN_URL}")
            sb.driver.get(LOGIN_URL)
            time.sleep(5)

            accept_cookies_if_present(sb)

            print("[INFO] 正在输入邮箱...")
            sb.wait_for_element('input[name="Email"]', timeout=15)
            sb.type('input[name="Email"]', USER_EMAIL)
            time.sleep(2)

            print("[INFO] 正在输入密码...")
            sb.wait_for_element('//*[@id="password"]', timeout=15)
            sb.type('//*[@id="password"]', FIXED_PASSWORD)
            time.sleep(2)

            print("[INFO] 启动登录页 Cloudflare 人机验证检测...")
            for cf_attempt in range(3):
                handle_cloudflare_turnstile(sb, f"登录页第 {cf_attempt + 1} 次")
                try:
                    cf_token = sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']").value')
                    if cf_token and len(cf_token.strip()) > 0:
                        print("[INFO] 登录页 Turnstile Token 验证成功注入！")
                        break
                except Exception:
                    pass
                time.sleep(3)

            print("[INFO] 正在点击登录按钮...")
            sb.click('button[type="submit"]')
            time.sleep(5)

            sb.save_screenshot(screenshot_path)
            send_telegram_message("📸 【步骤 1/2】账号登录表单已提交。", screenshot_path)

            # ==================== 第二步：进入后台并重置 ====================
            print(f"[INFO] 正在跳转到目标页面: {TARGET_URL}")
            sb.driver.get(TARGET_URL)
            time.sleep(5)

            sb.save_screenshot(screenshot_path)
            send_telegram_message("📸 【步骤 2/2】已跳转至目标后台页面现场。", screenshot_path)

            # 点击 Reset timer 按钮
            print("[INFO] 正在点击 Reset timer...")
            sb.wait_for_element('button[aria-label="Reset timer"]', timeout=20)
            sb.click('button[aria-label="Reset timer"]')

            print("[INFO] 等待 Reset 弹窗及 Turnstile 控件稳定加载...")
            time.sleep(4)

            sb.save_screenshot(screenshot_path)
            send_telegram_message("📸 【步骤 2/2】已点击 Reset timer 按钮，弹窗界面现场。", screenshot_path)

            # Reset 弹窗人机验证重试机制
            print("[INFO] 启动 Reset 弹窗 Cloudflare 人机验证检测...")
            for cf_attempt in range(4):
                handle_cloudflare_turnstile(sb, f"Reset 弹窗第 {cf_attempt + 1} 次")
                
                try:
                    cf_token = sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']").value')
                    if cf_token and len(cf_token.strip()) > 0:
                        print("[INFO] Reset 弹窗 Turnstile Token 验证成功注入！")
                        break
                except Exception:
                    pass
                time.sleep(3)

            # 查找并点击 Just Reset 按钮
            print("[INFO] 正在等待并查找 Just Reset 按钮...")
            just_reset_selector = 'xpath://button[contains(., "Just Reset")]'
            
            try:
                sb.wait_for_element(just_reset_selector, timeout=20)
                found_element = sb.find_element(just_reset_selector)
                
                if found_element:
                    outer_html = sb.driver.execute_script("return arguments[0].outerHTML;", found_element)
                    print("=" * 60)
                    print("[DEBUG] 成功捕获到 Just Reset 按钮 HTML：")
                    print(outer_html)
                    print("=" * 60)

                    print("[INFO] 正在点击 Just Reset 按钮...")
                    sb.click(just_reset_selector)
                else:
                    raise Exception("未找到元素对象")
            except Exception as e:
                sb.save_screenshot(screenshot_path)
                send_telegram_message(f"⚠️ 【异常现场】查找 Just Reset 按钮失败！报错: {e}", screenshot_path)
                raise Exception(f"未找到 Just Reset 按钮元素: {e}")

            time.sleep(3)

            # 读取剩余时间
            try:
                remaining_time_elem = sb.find_element('span.hidden.sm\\:inline')
                remaining_time_text = remaining_time_elem.text
                print(f"[INFO] 当前剩余时间: {remaining_time_text}")
            except Exception:
                remaining_time_text = "未能成功获取剩余时间"
                print(f"[WARN] {remaining_time_text}")

            # 检查 Start 按钮是否存在
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

            sb.save_screenshot(screenshot_path)
            msg = (
                f"🎉 【步骤 2/2】操作执行完成！\n"
                f"⏱️ 剩余时间: {remaining_time_text}\n"
                f"▶️ Start 按钮已点击: {'是' if start_clicked else '否'}"
            )
            send_telegram_message(msg, screenshot_path)
            print("[INFO] 所有步骤顺利执行完毕！")

    except Exception as e:
        error_msg = f"🚨 [ERROR] 任务执行过程中发生异常: {str(e)}"
        print(error_msg)
        screenshot_path = "step_screenshot.png"
        try:
            sb.save_screenshot(screenshot_path)
            send_telegram_message(error_msg, screenshot_path)
        except Exception:
            send_telegram_message(error_msg)
    finally:
        screenshot_path = "step_screenshot.png"
        if os.path.exists(screenshot_path):
            try:
                os.remove(screenshot_path)
            except Exception:
                pass

if __name__ == "__main__":
    main()
