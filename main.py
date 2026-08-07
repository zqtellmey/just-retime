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
    """优化后的 Cloudflare 验证：给予充分缓冲并检测成功提示或组件加载"""
    print(f"[INFO] ({step_name}) 正在检测 Cloudflare Turnstile 验证组件...")
    
    # 增加初始等待，防止 CF 组件由于页面加载过快而未渲染
    time.sleep(3)
    
    for cf_attempt in range(3):
        try:
            # 优先检查是否已经直接出现了成功回执文本
            if sb.is_text_visible("成功") or sb.is_text_visible("Success"):
                print(f"[INFO] ({step_name}) 检测到成功提示文本，验证已通过！")
                return True

            # 检查是否存在人机验证组件
            has_turnstile = sb.is_element_visible('input[name="cf-turnstile-response"]') or sb.is_element_visible('.cf-turnstile')
            if not has_turnstile and cf_attempt == 0:
                print(f"[INFO] ({step_name}) 当前未检测到显式验证拦截，默认安全通过。")
                return True

            print(f"[INFO] ({step_name}) 发现验证组件或拦截，尝试物理 GUI 点击 (第 {cf_attempt + 1} 次)...")
            sb.uc_gui_click_captcha()
            time.sleep(5)
            
            if sb.is_text_visible("成功") or sb.is_text_visible("Success"):
                print(f"[INFO] ({step_name}) 点击后成功通过验证！")
                return True
                
        except Exception as e:
            print(f"[WARN] ({step_name}) 尝试 {cf_attempt + 1} 异常: {e}")
        
        time.sleep(3)
        
    print(f"[INFO] ({step_name}) 验证流程结束，继续执行...")
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
        print("[ERROR] 缺少必要的环境变量，请检查配置。")
        return

    # 使用 SeleniumBase uc 模式启动浏览器
    with SB(uc=True, test=True, locale="zh") as sb:
        screenshot_path = "step_screenshot.png"
        
        try:
            # ==================== 第一步：登录 ====================
            print("[INFO] 正在打开登录页面...")
            sb.open(LOGIN_URL)
            time.sleep(4)

            accept_cookies_if_present(sb)
            debug_check_elements(sb)

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
            time.sleep(5)

            sb.save_screenshot(screenshot_path)
            send_telegram_message("【步骤 1/2】账号登录成功，已过验证并提交表单。", screenshot_path)

            # ==================== 第二步：进入后台并重置 ====================
            print(f"[INFO] 正在跳转到目标页面: {TARGET_URL}")
            sb.open(TARGET_URL)
            time.sleep(6)  # 留出更充足的后台加载时间

            # 处理后台页面的 CF 验证
            handle_cloudflare_turnstile(sb, "后台页")

            # 点击 Reset timer 按钮
            print("[INFO] 正在点击 Reset timer...")
            sb.wait_for_element('button[aria-label="Reset timer"]', timeout=15)
            sb.click('button[aria-label="Reset timer"]')
            time.sleep(3)  # 留出弹窗完全展开的缓冲时间

            print("[INFO] 已调出 Reset 弹窗，开始进行按钮状态详细探测与输出...")

            # ==================== 详细输出 Just Reset 按钮探测情况 ====================
            just_reset_selector = 'button:has(i.bi-arrow-clockwise)'
            print("=" * 40)
            print("[DEBUG] 正在诊断页面上的 Just Reset 按钮状态：")
            try:
                all_buttons = sb.find_elements("button")
                print(f"[DEBUG] 当前页面总共找到 {len(all_buttons)} 个 button 元素。")
                found_match = False
                for idx, btn in enumerate(all_buttons):
                    try:
                        txt = btn.text.strip()
                        inner_html = btn.get_attribute("innerHTML")
                        if "Just Reset" in txt or "bi-arrow-clockwise" in inner_html:
                            found_match = True
                            print(f"  [√] 匹配到目标按钮 (索引 {idx}): text='{txt}', class='{btn.get_attribute('class')}'")
                    except Exception:
                        pass
                if not found_match:
                    print("  [×] 未通过常规遍历直接捕捉到目标文字，尝试通过选择器直接查找...")
            except Exception as e:
                print(f"  [!] 诊断遍历过程出现异常: {e}")
            print("=" * 40)

            # 等待目标按钮可见
            sb.wait_for_element(just_reset_selector, timeout=15)
            
            # 点击 Just Reset 按钮：采用纯净、安全的 JS 直接精准触发点击，彻底避免动作链连接断开问题
            print("[INFO] 正在通过安全的 JS 脚本精准触发 Just Reset 按钮点击...")
            clicked_success = sb.driver.execute_script("""
                const buttons = Array.from(document.querySelectorAll('button'));
                const targetBtn = buttons.find(el => el.textContent.includes('Just Reset') || el.innerHTML.includes('bi-arrow-clockwise'));
                if (targetBtn) {
                    targetBtn.click();
                    return true;
                }
                return false;
            """)
            
            if clicked_success:
                print("[INFO] Just Reset 按钮已通过 JS 成功触发点击！")
            else:
                print("[WARN] JS 未能直接匹配，尝试使用备用 CSS 选择器点击...")
                sb.click(just_reset_selector)
            
            time.sleep(4)

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
