# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：  
# 1. 不得用于任何商业用途。  
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。  
# 3. 不得进行大规模爬取或对平台造成运营干扰。  
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。   
# 5. 不得用于任何非法或不当的用途。
#   
# 详细许可条款请参阅项目根目录下的LICENSE文件。  
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。  


import argparse

import config
from tools.utils import str2bool


async def parse_cmd():
    # 读取command arg
    parser = argparse.ArgumentParser(description='Media crawler program.')
    parser.add_argument('--platform', type=str, help='Media platform select (xhs | dy | ks | bili | weibo | tieba | zhihu)',
                        choices=["xhs", "dy", "ks", "bili", "weibo", "tieba", "zhihu"], default=config.PLATFORM)
    parser.add_argument('--lt', type=str, help='Login type (qrcode | phone | cookie)',
                        choices=["qrcode", "phone", "cookie"], default=config.LOGIN_TYPE)
    parser.add_argument('--type', type=str, help='crawler type (search | detail | creator)',
                        choices=["search", "detail", "creator"], default=config.CRAWLER_TYPE)
    parser.add_argument('--start', type=int,
                        help='number of start page', default=config.START_PAGE)
    parser.add_argument('--keywords', type=str,
                        help='please input keywords', default=config.KEYWORDS)
    parser.add_argument('--get_comment', type=str2bool,
                        help='''whether to crawl level one comment, supported values case insensitive ('yes', 'true', 't', 'y', '1', 'no', 'false', 'f', 'n', '0')''', default=config.ENABLE_GET_COMMENTS)
    parser.add_argument('--get_sub_comment', type=str2bool,
                        help=''''whether to crawl level two comment, supported values case insensitive ('yes', 'true', 't', 'y', '1', 'no', 'false', 'f', 'n', '0')''', default=config.ENABLE_GET_SUB_COMMENTS)
    parser.add_argument('--save_data_option', type=str,
                        help='where to save the data (csv or db or json)', choices=['csv', 'db', 'json'], default=config.SAVE_DATA_OPTION)
    parser.add_argument('--cookies', type=str,
                        help='cookies used for cookie login type', default=config.COOKIES)
    parser.add_argument('--save_file_timestamp', type=str,
                        help='custom save file timestamp (without extension)', default=None)
    parser.add_argument('--creator_id_list', type=str,
                        help='creator id list, comma separated, will override config.<PLATFORM>_CREATOR_ID_LIST', default=None)
    parser.add_argument('--specified_id_list', type=str,
                        help='specified id list, comma separated, will override config.<PLATFORM>_SPECIFIED_ID_LIST', default=None)
    parser.add_argument('--headless', type=str2bool,
                        help='whether to use headless browser mode', default=True)

    args = parser.parse_args()

    # override config
    config.PLATFORM = args.platform
    config.LOGIN_TYPE = args.lt
    config.CRAWLER_TYPE = args.type
    config.START_PAGE = args.start
    config.KEYWORDS = args.keywords
    config.ENABLE_GET_COMMENTS = args.get_comment
    config.ENABLE_GET_SUB_COMMENTS = args.get_sub_comment
    config.SAVE_DATA_OPTION = args.save_data_option
    config.COOKIES = args.cookies
    config.SAVE_FILE_TIMESTAMP = args.save_file_timestamp
    config.HEADLESS = args.headless

    # 自动适配平台 CREATOR_ID_LIST 字段
    if args.creator_id_list:
        platform_field_map = {
            'tieba': 'TIEBA_CREATOR_URL_LIST',
            'xhs': 'XHS_CREATOR_ID_LIST',
            'dy': 'DY_CREATOR_ID_LIST',
            'bili': 'BILI_CREATOR_ID_LIST',
            'ks': 'KS_CREATOR_ID_LIST',
            'zhihu': 'ZHIHU_CREATOR_URL_LIST',
            'weibo': 'WEIBO_CREATOR_ID_LIST',
        }
        field = platform_field_map.get(args.platform)
        id_list = [i.strip() for i in args.creator_id_list.split(',') if i.strip()]
        if field and hasattr(config, field):
            setattr(config, field, id_list)

    # 自动适配平台 SPECIFIED_ID_LIST 字段
    if args.specified_id_list:
        specified_field_map = {
            'tieba': 'TIEBA_SPECIFIED_ID_LIST',
            'xhs': 'XHS_SPECIFIED_NOTE_URL_LIST',
            'dy': 'DY_SPECIFIED_ID_LIST',
            'bili': 'BILI_SPECIFIED_ID_LIST',
            'ks': 'KS_SPECIFIED_ID_LIST',
            'zhihu': 'ZHIHU_SPECIFIED_ID_LIST',
            'weibo': 'WEIBO_SPECIFIED_ID_LIST',
        }
        field = specified_field_map.get(args.platform)
        id_list = [i.strip() for i in args.specified_id_list.split(',') if i.strip()]
        if field and hasattr(config, field):
            setattr(config, field, id_list)
