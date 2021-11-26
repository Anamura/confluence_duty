import requests
import json
import hvac
from itertools import cycle
from calendar import day_name
from datetime import datetime, timedelta, time
import config_master

config = config_master.load()
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

LOGIN_URL = config['confluence_url'] + '/login.action'
CALENDAR_URL = config['calendar_url']
CALENDAR_ID = config['calendar_id']


def login():
    session = requests.Session()
    login_url = LOGIN_URL
    cookies = session.get(login_url, verify=False).cookies
    client = hvac.Client(url=config['vault_url'], token=config['vault_token'], verify=False)
    secret = client.read(config['path'])['data']
    data = {"os_username": secret['data']['username'],
            "os_password": secret['data']['password']
            }
    page_login = session.post(login_url, cookies=cookies, data=data, verify=False)
    cookies = page_login.cookies
    return session, cookies


def get_calendar():
    session, cookies = login()
    url = CALENDAR_URL
    now = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    start = now.strftime(DATE_FORMAT)
    end = (now + timedelta(days=365)).strftime(DATE_FORMAT)
    data = {
        "subCalendarId": CALENDAR_ID,
        "userTimeZoneId": "Europe%2FMoscow",
        "start": start,
        "end": end,
    }
    page = session.get(url, cookies=cookies, params=data, verify=False)
    events = page.json()
    return events


def fill_shift():
    events = get_calendar()
    for event in events['events']:
        date = datetime.today().strftime('%b %d, %Y')

        # if event.get('allDay'):
        # end = end.replace(hour=23, minute=59, second=59)
        result = []
        if date in event["confluenceFormattedStartDate"]:
            for i in event["invitees"]:
                result.append('<@' + lookup_by_email(i['email']) + '>')

            return result


def lookup_by_email(email):
    headers = {'Content-Type': "application/json; charset=utf-8",
               'Authorization': "Bearer " + config['token']}
    result = requests.get(config['slack_url'] + '/api/users.lookupByEmail?email={0}'.format(email),
                          headers=headers, verify=False)
    return result.json().get('user')['name']


def add_event(person_list, sub_calendar_id):
    session, cookies = login()
    events = get_calendar()
    try:
        for event in events['events']:
            if event["id"] != '':
                delete_event(event["id"], session, cookies)
    except Exception as e:
        print(e)

    url = CALENDAR_URL
    header = {'Content-Type': "application/x-www-form-urlencoded"}

    pr = cycle(person_list)
    result = [next(pr) for _ in range(365)]
    for user, day in zip(result, get_days()):
        user_id = get_user_id(user, session, cookies)
        body = {
            "allDayEvent": "false",
            "eventType": "custom",
            "customEventTypeId": config['event'],
            "description": "",
            "className": "outage",
            "title": "I need help",
            "person": user_id,
            "what": "I need help",
            "startDate": day,
            "endDate": day,
            "startTime": "10:00",
            "endTime": "18:00",
            "subCalendarId": sub_calendar_id
        }
        if user_id is not None and sub_calendar_id != '':
            session.put(url, cookies=cookies, headers=header, data=body, verify=False)


def get_days():
    date = datetime.today()
    days = []
    for i in range(365):
        if day_name[date.weekday()] not in ['Saturday', 'Sunday']:
            days.append(date.strftime('%d-%b-%Y'))
        date += timedelta(days=1)
    return days


def get_user_id(user, session, cookies):
    header = {'Content-Type': "application/json; charset=utf-8"}
    result = session.get(config['confluence_url'] +
                         '/rest/api/user?username={0}&expand=details.personal,details.business'.format(user),
                         cookies=cookies, headers=header, verify=False)
    return result.json()['userKey']


def delete_event(uid, session, cookies):
    payload = {
        "subCalendarId": CALENDAR_ID,
        "uid": uid
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    url = CALENDAR_URL
    response = session.delete(url, cookies=cookies, data=payload, headers=headers, verify=False)
    return response.json()['success']
