# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：  
# 1. 不得用于任何商业用途。  
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。  
# 3. 不得进行大规模爬取或对平台造成运营干扰。  
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。   
# 5. 不得用于任何非法或不当的用途。
#   
# 详细许可条款请参阅项目根目录下的LICENSE文件。  
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。  


import asyncio
import functools
import sys
from typing import Optional

from playwright.async_api import BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from tenacity import (RetryError, retry, retry_if_result, stop_after_attempt,
                      wait_fixed)

import config
from base.base_crawler import AbstractLogin
from cache.cache_factory import CacheFactory
from tools import utils


class DouYinLogin(AbstractLogin):

    def __init__(self,
                 login_type: str,
                 browser_context: BrowserContext, # type: ignore
                 context_page: Page, # type: ignore
                 login_phone: Optional[str] = "",
                 cookie_str: Optional[str] = ""
                 ):
        config.LOGIN_TYPE = login_type
        self.browser_context = browser_context
        self.context_page = context_page
        self.login_phone = login_phone
        self.scan_qrcode_time = 60
        self.cookie_str = cookie_str

    async def begin(self):
        """
            Start login douyin website
            滑块中间页面的验证准确率不太OK... 如果没有特俗要求，建议不开抖音登录，或者使用cookies登录
        """
        
        # 如果登录类型是none，则只关闭登录对话框，不进行实际登录
        if config.LOGIN_TYPE == "none":
            utils.logger.info("[DouYinLogin.begin] Login type is 'none', only closing login dialog if exists...")
            await self.check_and_close_login_dialog()
            return

        # popup login dialog
        await self.popup_login_dialog()

        # select login type
        if config.LOGIN_TYPE == "qrcode":
            await self.login_by_qrcode()
        elif config.LOGIN_TYPE == "phone":
            await self.login_by_mobile()
        elif config.LOGIN_TYPE == "cookie":
            await self.login_by_cookies()
        else:
            raise ValueError("[DouYinLogin.begin] Invalid Login Type Currently only supported qrcode or phone or cookie ...")

        # 如果页面重定向到滑动验证码页面，需要再次滑动滑块
        await asyncio.sleep(6)
        current_page_title = await self.context_page.title()
        if "验证码中间页" in current_page_title:
            await self.check_page_display_slider(move_step=3, slider_level="hard")

        # check login state
        utils.logger.info(f"[DouYinLogin.begin] login finished then check login state ...")
        try:
            await self.check_login_state()
        except RetryError:
            utils.logger.info("[DouYinLogin.begin] login failed please confirm ...")
            sys.exit()

        # wait for redirect
        wait_redirect_seconds = 5
        utils.logger.info(f"[DouYinLogin.begin] Login successful then wait for {wait_redirect_seconds} seconds redirect ...")
        await asyncio.sleep(wait_redirect_seconds)

    @retry(stop=stop_after_attempt(600), wait=wait_fixed(1), retry=retry_if_result(lambda value: value is False))
    async def check_login_state(self):
        """Check if the current login status is successful and return True otherwise return False"""
        current_cookie = await self.browser_context.cookies()
        _, cookie_dict = utils.convert_cookies(current_cookie)

        for page in self.browser_context.pages:
            try:
                local_storage = await page.evaluate("() => window.localStorage")
                if local_storage.get("HasUserLogin", "") == "1":
                    return True
            except Exception as e:
                # utils.logger.warn(f"[DouYinLogin] check_login_state waring: {e}")
                await asyncio.sleep(0.1)

        if cookie_dict.get("LOGIN_STATUS") == "1":
            return True

        return False

    async def popup_login_dialog(self):
        """If the login dialog box does not pop up automatically, we will manually click the login button"""
        dialog_selector = "xpath=//div[@id='login-panel-new']"
        try:
            # check dialog box is auto popup and wait for 10 seconds
            await self.context_page.wait_for_selector(dialog_selector, timeout=1000 * 10)
        except Exception as e:
            utils.logger.error(f"[DouYinLogin.popup_login_dialog] login dialog box does not pop up automatically, error: {e}")
            utils.logger.info("[DouYinLogin.popup_login_dialog] login dialog box does not pop up automatically, we will manually click the login button")
            login_button_ele = self.context_page.locator("xpath=//p[text() = '登录']")
            await login_button_ele.click()
            await asyncio.sleep(0.5)

    async def login_by_qrcode(self):
        utils.logger.info("[DouYinLogin.login_by_qrcode] Begin login douyin by qrcode...")
        qrcode_img_selector = "xpath=//div[@id='animate_qrcode_container']//img"
        base64_qrcode_img = await utils.find_login_qrcode(
            self.context_page,
            selector=qrcode_img_selector
        )
        if not base64_qrcode_img:
            utils.logger.info("[DouYinLogin.login_by_qrcode] login qrcode not found please confirm ...")
            sys.exit()

        partial_show_qrcode = functools.partial(utils.show_qrcode, base64_qrcode_img)
        asyncio.get_running_loop().run_in_executor(executor=None, func=partial_show_qrcode)
        await asyncio.sleep(2)

    async def login_by_mobile(self):
        utils.logger.info("[DouYinLogin.login_by_mobile] Begin login douyin by mobile ...")
        mobile_tap_ele = self.context_page.locator("xpath=//li[text() = '验证码登录']")
        await mobile_tap_ele.click()
        await self.context_page.wait_for_selector("xpath=//article[@class='web-login-mobile-code']")
        mobile_input_ele = self.context_page.locator("xpath=//input[@placeholder='手机号']")
        await mobile_input_ele.fill(self.login_phone)
        await asyncio.sleep(0.5)
        send_sms_code_btn = self.context_page.locator("xpath=//span[text() = '获取验证码']")
        await send_sms_code_btn.click()

        # 检查是否有滑动验证码
        await self.check_page_display_slider(move_step=10, slider_level="easy")
        cache_client = CacheFactory.create_cache(config.CACHE_TYPE_MEMORY)
        max_get_sms_code_time = 60 * 2  # 最长获取验证码的时间为2分钟
        while max_get_sms_code_time > 0:
            utils.logger.info(f"[DouYinLogin.login_by_mobile] get douyin sms code from redis remaining time {max_get_sms_code_time}s ...")
            await asyncio.sleep(1)
            sms_code_key = f"dy_{self.login_phone}"
            sms_code_value = cache_client.get(sms_code_key)
            if not sms_code_value:
                max_get_sms_code_time -= 1
                continue

            sms_code_input_ele = self.context_page.locator("xpath=//input[@placeholder='请输入验证码']")
            await sms_code_input_ele.fill(value=sms_code_value.decode())
            await asyncio.sleep(0.5)
            submit_btn_ele = self.context_page.locator("xpath=//button[@class='web-login-button']")
            await submit_btn_ele.click()  # 点击登录
            # todo ... 应该还需要检查验证码的正确性有可能输入的验证码不正确
            break

    async def check_page_display_slider(self, move_step: int = 10, slider_level: str = "easy"):
        """
        检查页面是否出现滑动验证码
        :return:
        """
        # 等待滑动验证码的出现
        back_selector = "#captcha-verify-image"
        try:
            await self.context_page.wait_for_selector(selector=back_selector, state="visible", timeout=30 * 1000)
        except PlaywrightTimeoutError:  # 没有滑动验证码，直接返回
            return

        gap_selector = 'xpath=//*[@id="captcha_container"]/div/div[2]/img[2]'
        max_slider_try_times = 20
        slider_verify_success = False
        while not slider_verify_success:
            if max_slider_try_times <= 0:
                utils.logger.error("[DouYinLogin.check_page_display_slider] slider verify failed ...")
                sys.exit()
            try:
                await self.move_slider(back_selector, gap_selector, move_step, slider_level)
                await asyncio.sleep(1)

                # 如果滑块滑动慢了，或者验证失败了，会提示操作过慢，这里点一下刷新按钮
                page_content = await self.context_page.content()
                if "操作过慢" in page_content or "提示重新操作" in page_content:
                    utils.logger.info("[DouYinLogin.check_page_display_slider] slider verify failed, retry ...")
                    await self.context_page.click(selector="//a[contains(@class, 'secsdk_captcha_refresh')]")
                    continue

                # 滑动成功后，等待滑块消失
                await self.context_page.wait_for_selector(selector=back_selector, state="hidden", timeout=1000)
                # 如果滑块消失了，说明验证成功了，跳出循环，如果没有消失，说明验证失败了，上面这一行代码会抛出异常被捕获后继续循环滑动验证码
                utils.logger.info("[DouYinLogin.check_page_display_slider] slider verify success ...")
                slider_verify_success = True
            except Exception as e:
                utils.logger.error(f"[DouYinLogin.check_page_display_slider] slider verify failed, error: {e}")
                await asyncio.sleep(1)
                max_slider_try_times -= 1
                utils.logger.info(f"[DouYinLogin.check_page_display_slider] remaining slider try times: {max_slider_try_times}")
                continue

    async def move_slider(self, back_selector: str, gap_selector: str, move_step: int = 10, slider_level="easy"):
        """
        Move the slider to the right to complete the verification
        :param back_selector: 滑动验证码背景图片的选择器
        :param gap_selector:  滑动验证码的滑块选择器
        :param move_step: 是控制单次移动速度的比例是1/10 默认是1 相当于 传入的这个距离不管多远0.1秒钟移动完 越大越慢
        :param slider_level: 滑块难度 easy hard,分别对应手机验证码的滑块和验证码中间的滑块
        :return:
        """

        # get slider background image
        slider_back_elements = await self.context_page.wait_for_selector(
            selector=back_selector,
            timeout=1000 * 10,  # wait 10 seconds
        )
        slide_back = str(await slider_back_elements.get_property("src")) # type: ignore

        # get slider gap image
        gap_elements = await self.context_page.wait_for_selector(
            selector=gap_selector,
            timeout=1000 * 10,  # wait 10 seconds
        )
        gap_src = str(await gap_elements.get_property("src")) # type: ignore

        # 识别滑块位置
        slide_app = utils.Slide(gap=gap_src, bg=slide_back)
        distance = slide_app.discern()

        # 获取移动轨迹
        tracks = utils.get_tracks(distance, slider_level)
        new_1 = tracks[-1] - (sum(tracks) - distance)
        tracks.pop()
        tracks.append(new_1)

        # 根据轨迹拖拽滑块到指定位置
        element = await self.context_page.query_selector(gap_selector)
        bounding_box = await element.bounding_box() # type: ignore

        await self.context_page.mouse.move(bounding_box["x"] + bounding_box["width"] / 2, # type: ignore
                                           bounding_box["y"] + bounding_box["height"] / 2) # type: ignore
        # 这里获取到x坐标中心点位置
        x = bounding_box["x"] + bounding_box["width"] / 2 # type: ignore
        # 模拟滑动操作
        await element.hover() # type: ignore
        await self.context_page.mouse.down()

        for track in tracks:
            # 循环鼠标按照轨迹移动
            # steps 是控制单次移动速度的比例是1/10 默认是1 相当于 传入的这个距离不管多远0.1秒钟移动完 越大越慢
            await self.context_page.mouse.move(x + track, 0, steps=move_step)
            x += track
        await self.context_page.mouse.up()

    async def login_by_cookies(self):
        utils.logger.info("[DouYinLogin.login_by_cookies] Begin login douyin by cookie ...")
        for key, value in utils.convert_str_cookie_to_dict(self.cookie_str).items():
            await self.browser_context.add_cookies([{
                'name': key,
                'value': value,
                'domain': ".douyin.com",
                'path': "/"
            }])

    async def close_login_dialog(self):
        """
        关闭抖音登录对话框
        Close the Douyin login dialog box
        """
        utils.logger.info("[DouYinLogin.close_login_dialog] Attempting to close login dialog...")
        
        # 常见的登录框关闭按钮选择器
        close_selectors = [
            "xpath=//*[@id='douyin_login_comp_flat_panel']/div/div[1]/div[2]"
        ]
        
        # 尝试点击关闭按钮
        for selector in close_selectors:
            try:
                # 等待元素出现，超时时间设为2秒
                await self.context_page.wait_for_selector(selector, timeout=2000)
                close_button = self.context_page.locator(selector)
                
                # 检查元素是否可见和可点击
                if await close_button.is_visible():
                    await close_button.click()
                    utils.logger.info(f"[DouYinLogin.close_login_dialog] Successfully clicked close button with selector: {selector}")
                    await asyncio.sleep(1)  # 等待对话框关闭动画完成
                    return True
                    
            except Exception as e:
                # 如果当前选择器没找到元素，继续尝试下一个
                continue
        
        # 如果找不到关闭按钮，尝试按ESC键关闭
        try:
            utils.logger.info("[DouYinLogin.close_login_dialog] No close button found, trying ESC key...")
            await self.context_page.keyboard.press('Escape')
            await asyncio.sleep(1)
            utils.logger.info("[DouYinLogin.close_login_dialog] Pressed ESC key to close dialog")
            return True
        except Exception as e:
            utils.logger.error(f"[DouYinLogin.close_login_dialog] Failed to press ESC key: {e}")
        
        # 如果ESC键也不行，尝试点击对话框外部区域关闭
        try:
            utils.logger.info("[DouYinLogin.close_login_dialog] Trying to click outside dialog to close...")
            # 点击页面左上角（通常在对话框外部）
            await self.context_page.click('body', position={'x': 50, 'y': 50})
            await asyncio.sleep(1)
            utils.logger.info("[DouYinLogin.close_login_dialog] Clicked outside dialog area")
            return True
        except Exception as e:
            utils.logger.error(f"[DouYinLogin.close_login_dialog] Failed to click outside dialog: {e}")
        
        utils.logger.warning("[DouYinLogin.close_login_dialog] All methods to close login dialog failed")
        return False

    async def check_and_close_login_dialog(self):
        """
        检查是否存在登录对话框，如果存在则关闭它
        Check if login dialog exists and close it if found
        """
        utils.logger.info("[DouYinLogin.check_and_close_login_dialog] Checking for login dialog...")
        
        # 登录对话框的选择器
        dialog_selectors = [
            "xpath=//div[@id='login-panel-new']",
            "xpath=//div[contains(@class, 'login') and contains(@class, 'modal')]",
            "xpath=//div[contains(@class, 'login') and contains(@class, 'dialog')]",
            "xpath=//div[contains(@class, 'login-modal')]",
            "css=.login-panel",
            "css=.login-modal",
        ]
        
        # 检查是否存在登录对话框
        for selector in dialog_selectors:
            try:
                # 等待元素出现，超时时间设为1秒
                await self.context_page.wait_for_selector(selector, timeout=1000)
                dialog_element = self.context_page.locator(selector)
                
                # 检查对话框是否可见
                if await dialog_element.is_visible():
                    utils.logger.info(f"[DouYinLogin.check_and_close_login_dialog] Found login dialog with selector: {selector}")
                    # 尝试关闭对话框
                    success = await self.close_login_dialog()
                    if success:
                        utils.logger.info("[DouYinLogin.check_and_close_login_dialog] Login dialog closed successfully")
                        return True
                    else:
                        utils.logger.warning("[DouYinLogin.check_and_close_login_dialog] Failed to close login dialog")
                        return False
                        
            except Exception as e:
                # 如果当前选择器没找到元素，继续尝试下一个
                continue
        
        utils.logger.info("[DouYinLogin.check_and_close_login_dialog] No login dialog found")
        return True  # 没有找到登录对话框也算成功
