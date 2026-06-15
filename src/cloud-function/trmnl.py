#!/usr/bin/env python
# coding: utf-8

import functions_framework

import requests
import json
import datetime
import random

from collections import defaultdict
from collections import namedtuple

VERBOSE=False

HEADERS = {
    'Content-Type': 'application/json; charset=utf-8',
    'X-Parachutes': 'parachutes are cool',
    # 'Access-Control-Allow-Origin': '*'
}


def get_live_data_from_ruter(entur_stop:str = "NSR:StopPlace:58189", minutes_to_fetch:int = 30, ignore_departures_within_the_next_minutes:int = 0, fetch_limit:int = 200):
    url = 'https://api.entur.io/journey-planner/v3/graphql'

    headers = {
        'accept': 'application/json, text/plain, */*',
        'et-client-name': 'private-dashboard',
        'X-contact': 'cloessl@gmail.com'
    }

    current_time = datetime.datetime.now(datetime.UTC)
    future_time = current_time + datetime.timedelta(minutes=ignore_departures_within_the_next_minutes)
    formatted_time = future_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    if (VERBOSE):
        print(current_time)
        print(future_time)
        print(formatted_time)

    start_time = formatted_time
    seconds_to_fetch = minutes_to_fetch * 60

    payload = {
        "query": f"""
        fragment estimatedCallsParts on EstimatedCall {{
            destinationDisplay {{
                frontText
            }}
            situations {{
                summary {{
                    value
                    language
                }}
            }}
            quay {{
                publicCode
            }}
            expectedDepartureTime
            actualDepartureTime
            aimedDepartureTime
            serviceJourney {{
                line {{
                    publicCode
                    transportMode
                }}
            }}
        }}
        query {{
            board1: stopPlaces(ids: ["{entur_stop}"]) {{
                name
                estimatedCalls(startTime: "{start_time}" whiteListedModes: [rail,bus,metro,tram,water,coach], numberOfDepartures: {fetch_limit}, arrivalDeparture: departures, includeCancelledTrips: true, timeRange: {seconds_to_fetch}) {{
                    ...estimatedCallsParts
                }}
            }}
        }}
        """
    }

    response = requests.post(url, headers=headers, json=payload)

    try:
        jdata = response.json()
    except Exception as e:
        print(f"status code: {response.status_code}")
        print(f"response: {response}")
        return ("Error fetching data from ruter…", [])

    try:
        data = jdata['data']['board1'][0]['estimatedCalls']
        station_name = jdata['data']['board1'][0]['name']
    except Exception as e:
        print(f"Payload:\n{payload}")
        print(f"Response:\n{jdata}")
        print(f"An error occurred:\n{e}")
        print("Exiting...")
        exit()

    if (VERBOSE):
        print(f"Setting max res: {fetch_limit}")
        print(f"Setting minutes: {minutes_to_fetch}")
        print(f"Current time   : {current_time}")
        print(f"Future    time : {future_time}")
        print(f"Requested time : {formatted_time}")
        print(f"Status Code.   : {response.status_code}")
        print(f"Res, dep. times: {len(jdata['data']['board1'][0]['estimatedCalls'])}")
        print(f"Payload:\n{payload}")

    return (station_name, data)


# Converts
# 2025-03-19T22:36:00+01:00 -> 22:36.00
def iso_time_to_human(iso_date_time: str) -> str:
    dt = datetime.datetime.fromisoformat(iso_date_time)
    return dt.strftime("%H:%M.%S")


# Sort by
# * Local transport (they are int numbers, instead of FB1A)
# * Line number
# * Platform (so that busses going in the same direction/same platform are grouped together)
# * Destination (not sure that's still needed)
def sort_key(item):
    bus_line = item[0].line
    platform = item[0].platform
    bus_dest = item[0].dst
    local_first = isinstance(bus_line, str)  # Make sure lined routes are before FB1, etc.
    return (local_first, bus_line, platform, bus_dest)


# Just for debugging to print an item from a dict
def rnd(dictionary):
    key = random.choice(list(dictionary.keys()))
    print(type(key))
    print(type(dictionary[key]))
    print(key)
    print(dictionary[key])


def print_pretty_dep_times(list):
    for (line, line_dst, platform), items in list:
        trans_type = items[0]['type']
        print(f"Line: {line}, To: {line_dst}, Platform: {platform}, Type: {trans_type}")
        for item in items:
            # print(f"  {item}")
            print(f"\t{item['schedule']} - {item['expected']}")


def create_stripped_item(data):
    stripped_item = {
        # "dest": data["destinationDisplay"]["frontText"],
        # "situations": data["situations"],
        # "plat": data["quay"]["publicCode"],
        "schedule": iso_time_to_human(data["aimedDepartureTime"]),
        "expected": iso_time_to_human(data["expectedDepartureTime"]),
        # "line": data["serviceJourney"]["line"]["publicCode"],
        "type": data["serviceJourney"]["line"]["transportMode"]
    }
    return stripped_item


def group_data_by_line_dst_platform(data):
    # Parse data into a dictionary with an Tuple Index to be able to sort it the way we want
    # Format:
    # (bus_line, bus_dest, platform): [departure times details]
    grouped_data = defaultdict(list)
    Index = namedtuple('Index', ['line', 'dst', 'platform'])

    for item in data:
        line = item['serviceJourney']['line']['publicCode']
        line = int(line) if line.isdigit() else line
        quay_public_code = item['quay']['publicCode']
        line_dst = item['destinationDisplay']['frontText']
        index = Index(line, line_dst, quay_public_code)
        grouped_data[index].append(create_stripped_item(item))

    grouped_data = dict(grouped_data)
    return grouped_data


def main(entur_stop: str = "NSR:StopPlace:58366", exclude_platforms: str = "", fetch_limit: int = 200, minutes_to_fetch: int = 30, ignore_departures_within_the_next_minutes:int = 0):
    # Defensive programming: Make sure that strings parsed get correctly converted to int
    minutes_to_fetch = int(minutes_to_fetch) if isinstance(minutes_to_fetch, str) and minutes_to_fetch.isdigit() else 30

    # Get data from ruter
    station_name, data = get_live_data_from_ruter(minutes_to_fetch=minutes_to_fetch, entur_stop=entur_stop, fetch_limit=fetch_limit, ignore_departures_within_the_next_minutes=ignore_departures_within_the_next_minutes)
    # Group by bus_line, bus_dest, platform
    grouped_data = group_data_by_line_dst_platform(data)
    # Sort the grouped dict into a list
    sorted_items = sorted(grouped_data.items(), key=sort_key)  # returns list of tuples, [(Index, <Item>)]

    # Remove exclusion platforms
    exclusion_platform_list = exclude_platforms.split(',')
    cleaned_sorted_items = [item for item in sorted_items if item[0][2] not in exclusion_platform_list]

    # Generate departures json block in the format I want on trmnl
    platform_departures = defaultdict(dict)
    for item in cleaned_sorted_items:
        # item[0] Index Tuple, the key
        # item[1] Actual item/sparse data for departures
        platform_info_if_available =  f" - {item[0].platform}" if item[0].platform != None else ""
        platform_departures[item[0].line][f"{item[0].dst}{platform_info_if_available}"] = item[1]

    # Add some nice to have goodie stats
    return_json = {
        'departures': platform_departures,
        'last_updated': datetime.datetime.now(datetime.UTC).strftime("%H:%M"),
        'minutes_to_fetch': minutes_to_fetch,
        'num_departures': len(data),
        'num_departures-excludes': sum(len(sublist[1]) for sublist in cleaned_sorted_items),
        'name': station_name,
        'exclude_platforms': exclude_platforms,
        'fetch_limit': fetch_limit
    }

    if (VERBOSE):
        print("Full list.  : ", len(sorted_items))
        print("Cleaned list: ", len(cleaned_sorted_items))
        print_pretty_dep_times(sorted_items)
        print_pretty_dep_times(cleaned_sorted_items)
        print(json.dumps(return_json, indent=2))

    return json.dumps(return_json)


# Cloud function start point
@functions_framework.http
def http(request):
    """HTTP Cloud Function.
    Args:
        request (flask.Request): The request object.
        <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`
        <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
    """
    request_json = request.get_json(silent=True)
    request_args = request.args

    if 'secret' not in request_args or request_args['secret'] != 'public':
        return ('denied', 403, HEADERS)

    stop = request_args['stop'] if 'stop' in request_args and request_args['stop'] else "NSR:StopPlace:58366"  # Jernbanetorget: NSR:StopPlace:58366, Oslo S: NSR:StopPlace:59872, Kringsjå NSR:StopPlace:59706
    exclude = request_args['exclude_platforms'] if 'exclude_platforms' in request_args else ""
    minutes_to_fetch = request_args['minutes_to_fetch'] if 'minutes_to_fetch' in request_args and request_args['minutes_to_fetch'] else 30

    main_ret_json = main(entur_stop=stop, exclude_platforms=exclude, minutes_to_fetch=minutes_to_fetch, ignore_departures_within_the_next_minutes=3)
    return (main_ret_json, 200, HEADERS)


# local run start point
if __name__ == "__main__":
    # Run in verbose mode when called from console
    VERBOSE = True

    # main(entur_stop="NSR:StopPlace:11356", exclude_platforms="A,B", minutes_to_fetch=90, ignore_departures_within_the_next_minutes=5)  # No platform info available
    # main(entur_stop="NSR:StopPlace:58366", exclude_platforms="", minutes_to_fetch=7, ignore_departures_within_the_next_minutes=15)  # int check for minutes_to_fetch
    # main(entur_stop="NSR:StopPlace:58366", exclude_platforms="", minutes_to_fetch="29", ignore_departures_within_the_next_minutes=15)  # str check for minute_to_fetch

    # Default test for home
    main(entur_stop="NSR:StopPlace:58189", exclude_platforms="A,B", minutes_to_fetch=30, ignore_departures_within_the_next_minutes=15)
