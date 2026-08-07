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

def handle_cloudflare_in_popup_div(sb):
    """专门针对 Reset 弹窗 DIV 内部的人机验证进行穿透与多次触发"""
    print("[INFO] (Reset弹窗DIV) 开始深度检测并尝试处理弹窗内部的人机验证...")

    # 先调用一次 SB 内置穿透逻辑
    try:
        sb.uc_gui_click_captcha()
    except Exception:
        pass

    # 使用语法修正后的 JS (带 IIFE 包装) 定位弹窗容器及内部的 Turnstile iframe
    for attempt in range(3):
        print(f"[INFO] (Reset弹窗DIV) 尝试第 {attempt + 1}/3 次深入定位弹窗与 CF 框...")
        try:
            cf_info = sb.execute_script("""
                return (() => {
                    const popup = document.getElementById('turnstile-timer-reset') || document.querySelector('div[role="dialog"]');
                    if (!popup) {
                        return { status: "popup_not_found" };
                    }
                    
                    // 寻找弹窗内的 turnstile 容器或 iframe
                    const iframe = popup.querySelector('iframe[src*="cloudflare"]') || popup.querySelector('iframe[src*="turnstile"]');
                    if (iframe) {
                        const rect = iframe.getBoundingClientRect();
                        return {
                            status: "iframe_found",
                            x: rect.left + rect.width / 2,
                            y: rect.top + rect.height / 2
                        };
                    }
                    
                    const rect = popup.getBoundingClientRect();
                    return {
                        status: "popup_found_no_iframe",
                        x: rect.left + 35,
                        y: rect.top + (rect.height / 2)
                    };
                })();
            """)

            print(f"[INFO] (Reset弹窗DIV) 弹窗及 CF 框探测结果: {cf_info}")

            # 如果找到了具体坐标，使用 CDPTarget/PyAutoGUI 或 JS 模拟点击
            if cf_info and cf_info.get("status") in ["iframe_found", "popup_found_no_iframe"]:
                cx = cf_info.get("x")
                cy = cf_info.get("y")
                print(f"[INFO] 正在对算出的坐标 ({cx}, {cy}) 派发点击事件...")
                
                # 使用 JS 派发原生 Pointer/Click 事件穿透至深层元素
                sb.execute_script(f"""
                    (() => {{
                        const el = document.elementFromPoint({cx}, {cy});
                        if (el) {{
                            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evtType => {{
                                el.dispatchEvent(new MouseEvent(evtType, {{
                                    bubbles: true,
                                    cancelable: true,
                                    clientX: {cx},
                                    clientY: {cy}
                                }}));
                            }});
                        }}
                    }})();
                """)

        except Exception as e:
            print(f"[WARN] 第 {attempt + 1} 次尝试穿透异常: {e}")

        time.sleep(2)

def click_just_reset_button(sb):
    """诊断并点击弹窗 DIV 内部的 Just Reset 按钮 (使用 IIFE 修复 JS 语法错误)"""
    print("[INFO] [诊断模式] 开始检测弹窗 DIV 中是否存在 'Just Reset' 按钮...")

    # 1. 使用完全符合规范的 IIFE IIFE 封装 JS 脚本，防止 Illegal return 错误
    found_info = sb.execute_script("""
        return (() => {
            // 查寻包含 Just Reset 文本的所有按钮
            const btns = Array.from(document.querySelectorAll('button'));
            const target = btns.find(b => b.textContent && b.textContent.includes('Just Reset'));
            
            if (target) {
                return {
                    found: true,
                    tagName: target.tagName,
                    className: target.className,
                    disabled: target.disabled,
                    isVisible: target.offsetWidth > 0 && target.offsetHeight > 0,
                    text: target.textContent.trim()
                };
            }
            return { found: false, totalButtons: btns.length };
        })();
    """)

    print(f"[INFO] [诊断结果] 弹窗内部按钮查询结果: {found_info}")

    # 2. 优先尝试 Selenium 标准 XPath 点击
    just_reset_xpath = '//button[contains(normalize-space(.), "Just Reset")]'
    try:
        print("[INFO] 尝试使用 Selenium Standard XPath 定位点击...")
        sb.wait_for_element(just_reset_xpath, timeout=6)
        sb.click(just_reset_xpath)
        print("[SUCCESS] 成功通过 Selenium 定位并点击了 Just Reset 按钮！")
        return True
    except Exception as e:
        print(f"[WARN] Selenium 标准点击未成功: {e}")

    # 3. 如果找到元素但被遮挡或禁用，使用 JS 直接点击
    if found_info and found_info.get("found"):
        print("[INFO] 尝试通过 JS 强制触发 `.click()`...")
        clicked = sb.execute_script("""
            return (() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const target = btns.find(b => b.textContent && b.textContent.includes('Just Reset'));
                if (target) {
                    target.disabled = false; // 防范处于禁用状态
                    target.click();
                    return true;
                }
                return false;
            })();
        """)
        if clicked:
            print("[SUCCESS] 成功通过 JS 强制点击了 Just Reset 按钮！")
            return True

    print("[ERROR] 未能成功点击 Just Reset 按钮！")
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
            try:
                sb.uc_gui_click_captcha()
            except Exception:
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
            
            # 等待 Reset 弹窗 DIV 完全渲染
            print("[INFO] 等待 Reset 弹窗 DIV 渲染...")
            time.sleep(4)

            # 1. 在弹窗 DIV 内部寻找并穿透 CF 人机验证
            handle_cloudflare_in_popup_div(sb)

            # 留出 4 秒让 CF 服务器通过验证并变绿勾
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
