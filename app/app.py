import asyncio
import json
import logging
import os
import uuid

import aiofiles
import httpx
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.remote_connection import LOGGER

logger = logging.getLogger()
logger.setLevel(logging.INFO)

LOGGER.setLevel(logging.WARNING)
BOT_TOKEN = os.environ.get(
    'TG_BOT_TOKEN'
)
DTEK_SHUTDOWN_PAGE = 'https://www.dtek-dnem.com.ua/ua/shutdowns'

send_photo_url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto'
send_message_url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'


async def send_data(chat_id, file_path):
    logger.info(f'Opening file')
    rb_photo = open(file_path, 'rb')
    data = {'chat_id': chat_id}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            send_photo_url, data=data, files={'photo': rb_photo}
        )
        logger.info(f'Send photo response - {response.json()}')
    return response.status_code


async def paste_value_and_click(driver, input_xpath, address_value, button_xpath):
    # Find an input field, enter text and click on it
    await asyncio.sleep(2.5)
    input_field = driver.find_element('xpath', input_xpath)
    await asyncio.get_event_loop().run_in_executor(
        None, input_field.send_keys, address_value
    )

    # Find and click a button
    button = driver.find_element(
        'xpath', button_xpath
    )
    await asyncio.get_event_loop().run_in_executor(None, button.click)


async def get_user_power_cuts_schedule(city, street, house):
    chrome_options = Options()
    chrome_options.binary_location = '/opt/chrome/chrome'
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-dev-tools')
    chrome_options.add_argument('--no-zygote')
    chrome_options.add_argument('--single-process')
    chrome_options.add_argument('--user-data-dir=/tmp/chrome-user-data')
    chrome_options.add_argument('--remote-debugging-port=9222')
    chrome_options.add_argument('window-size=1920,1080')

    driver = webdriver.Chrome('/opt/chromedriver', options=chrome_options)

    # Navigate to a web page
    driver.get(DTEK_SHUTDOWN_PAGE)

    while True:
        try:
            await paste_value_and_click(driver, '//*[@id="city"]', city, '//*[@id="cityautocomplete-list"]/div')
            break
            # Wait for page to load
        except NoSuchElementException as error:
            logger.error(f'Page not loaded: {error}')

    await paste_value_and_click(driver, '//*[@id="street"]', street, '//*[@id="streetautocomplete-list"]/div')

    await paste_value_and_click(driver, '//*[@id="house_num"]', house, '//*[@id="house_numautocomplete-list"]/div[1]')

    # Get the page source
    table_binary = driver.find_element(
        'xpath', '//*[@id="6685"]/section'
    ).screenshot_as_png
    logger.info(f'Table binary screenshot part - {table_binary[:3]}')

    # Quit the browser
    driver.quit()

    return table_binary


async def write_image(binary_string):
    random_file_name = uuid.uuid4()
    image_path = f'/tmp/{random_file_name}.png'
    async with aiofiles.open(image_path, 'wb') as photo:
        logger.info(f'Writing image to {image_path}')
        await photo.write(binary_string)
        return image_path


async def send_message(url, chat_id, text):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            data={'chat_id': chat_id, 'text': text},
        )
        logger.info(f'Send message response - {response.json()}')


async def main(event, context):
    try:
        logger.info(f"Lambda invoked with {event=}")
        logger.info(f"Lambda invoked with {context=}")

        body = json.loads(event['body'])
        user_address = body['message'].get('text')
        user_chat_id = body['message']['chat']['id']
        user_first_name = body['message']['chat']['first_name']
        logger.info(f"User first name - {user_first_name}")
        logger.info(f"User chat id - {user_chat_id}")
        logger.info(f"User chat address - {user_address}")

        user_city, user_street, user_house = map(
            lambda address: address.strip(), user_address.split(',')
        )

        hi_message = f"Привіт, {user_first_name}! " \
                     f"Створюю графік відключень для адресси - {user_city}, {user_street}, {user_house}.."
        await send_message(send_message_url, chat_id=user_chat_id, text=hi_message)

        power_cuts_schedule_binary = await get_user_power_cuts_schedule(
            user_city, user_street, user_house
        )

        user_image_path = await write_image(power_cuts_schedule_binary)

        await send_data(user_chat_id, user_image_path)

        logger.info('Image sent')
        return {
            'statusCode': 200,
            'message': f'message sent to {user_chat_id=}',
        }
    except Exception as error:
        error_message = "Бот тимчасово не працює, спробуйте пізніше :("
        await send_message(send_message_url, chat_id=user_chat_id, text=error_message)
        logger.error(f'Error - {error}')
        return {'statusCode': 200, 'message': f'{error=}'}


def handler(event, context):
    return asyncio.run(main(event, context))
