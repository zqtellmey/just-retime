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

def draw_red_dot_on_screenshot(image_path, x, y, radius=15):
    """在指定坐标 (x, y) 处画一个醒目的红点，用于可视化点击位置"""
    try:
        if not os.path.exists(image_path):
            return
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill="red", outline="white", width=4)
        img.save(image_path)
        print(f"[DEBUG] 成功在校准坐标 ({x}, {y}) 处绘制红点。")
    except Exception as e:
        print(f"[WARN] 绘制红点失败: {e}")

def handle_cloudflare_turnstile(sb, step_name=""):
    """
    带坐标校准的过 CF 人机验证逻辑
    针对弹窗环境，自动对 iframe 坐标进行向下偏移校准，精确点击复选框
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
        
        print(f"[INFO] {prefix}发现 Turnstile 拦截，准备进行精准坐标校准点击...")

        # 🎯 核心校准逻辑：获取 Turnstile 容器坐标，并根据弹窗布局进行像素偏移修正
        target_x, target_y = None, None
        try:
            box_coords = sb.driver.execute_script("""
                const el = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                if (el) {
                    const rect = el.getBoundingClientRect();
                    return {
                        left: rect.left,
                        top: rect.top,
                        width: rect.width,
                        height: rect.height
                    };
                }
                return null;
            """)
            if box_coords:
                # 依据页面布局：iframe 中心偏上，我们需要将点击点往下、往左微调到复选框位置
                # 根据截图 3.jpg 比例：复选框在 iframe 内部靠左侧中间
                target_x = int(box_coords['left'] + box_coords['width'] * 0.25) # 往左偏一点到复选框
                target_y = int(box_coords['top'] + box_coords['height'] * 0.5)  # 垂直居中
                
                print(f"[INFO] 计算出校准后的精准点击坐标: ({target_x}, {target_y})")
        except Exception as coord_err:
            print(f"[DEBUG] 坐标计算失败: {coord_err}")

        # 如果成功计算出校准坐标，直接使用 SeleniumBase 的底层 GUI 绝对坐标点击
        if target_x and target_y:
            sb.save_screenshot(screenshot_path)
            draw_red_dot_on_screenshot(screenshot_path, target_x, target_y)
            send_telegram_message(f"🎯 <b>[校准红点]</b> {step_name} 修正后的复选框点击位置", screenshot_path)

            # 使用 SeleniumBase 的底层 GUI 点击指定绝对坐标
            sb.uc_gui_click_x_y(target_x, target_y)
        else:
            # 降级使用默认点击
            sb.uc_gui_click_captcha()

        time.sleep(3)

        # 校验 Token 是否注入成功
        token = sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']")?.value')
        if token and len(token.strip()) > 0:
            print(f"[INFO] {prefix}校准点击成功，Token 已成功注入！")
            return True

        # 2. 备用降级：精准切入 iframe 内部点击
        print(f"[INFO] {prefix}物理点击未生效，尝试切入 iframe 内部 DOM 点击...")
        iframes = sb.find_elements('iframe[src*="challenges.cloudflare.com"]')
        for idx, frame in enumerate(iframes):
            try:
                sb.switch_to_frame(frame)
                time.sleep(1)
                
                selectors = ['#challenge-stage', 'input[type="checkbox"]', '.ctp-checkbox-label', 'span.mark', '#cb-i']
                for target_sel in selectors:
                    if sb.is_element_visible(target_sel):
                        sb.uc_click(target_sel, reconnect_time=2)
                        time.sleep(2)
                        break

                sb.switch_to_parent_frame()
                token_check = sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']")?.value')
                if token_check and len(token_check.strip()) > 0:
                    return True
            except Exception:
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
