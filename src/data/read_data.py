# -*- coding: utf-8 -*-
from ..imports import *


def read_b_data(filename):
    """Read Berkeley earth .txt file data. Return a dataframe and city information.

    Create a datetime column with local timezone.

    """
    # read data file
    data_df = pd.read_csv(filename, sep='\t',
                          header=None, skiprows=10)

    # inspecting the top of the files to get the timezone
    with open(filename, 'r') as f:
        city_info = {}
        for i in range(9):
            line = f.readline()
            # remove %
            line = line.replace('% ', '')
            line = line.replace('\n', '')
            k, v = line.split(': ')
            city_info[k] = v
    time_zone = city_info['Time Zone']
    # assemble datetime column
    data_df['datetime'] = pd.to_datetime(
        {'year': data_df[0], 'month': data_df[1], 'day': data_df[2], 'hour': data_df[3]})
    # convert to Bangkok time zone and remove the time zone information
    data_df['datetime'] = data_df['datetime'].dt.tz_localize(
        'UTC').dt.tz_convert(time_zone)
    data_df['datetime'] = data_df['datetime'].dt.tz_localize(None)
    # drop Year, month, day, UTC hours, PM10_mask columns
    data_df = data_df.drop([0, 1, 2, 3, 5, 6], axis=1)
    data_df.columns = ['PM2.5', 'datetime']

    # inspecting the top of the files
    with open(filename, 'r') as f:
        city_info = {}
        for i in range(9):
            line = f.readline()
            # remove %
            line = line.replace('% ', '')
            line = line.replace('\n', '')
            k, v = line.split(': ')
            city_info[k] = v

    return data_df, city_info


def build_us_em_data(city_name: str, data_folder: str = '../data/us_emb/'):
    """Combine the pollution data from US Embassy monitoring station for the city. Return a list of pollution dataframe.

    """
    if city_name not in ['Hanoi', 'Jakarta']:
        raise AssertionError(f'no data for {city_name}')

    if city_name == 'Jakarta':
        name_list = ['JakartaCentral', 'JakartaSouth']
    else:
        name_list = ['Hanoi']

    data_list = []

    for name in name_list:
        files = glob(f'{data_folder}{name}*.csv')

        data = pd.DataFrame()
        # concatenate all data
        for file in files:
            df = pd.read_csv(file)
            data = pd.concat([data, df])
        # format the data
        data['Parameter'] = data['Parameter'].str.split(' - ', expand=True)[0]
        data['datetime'] = pd.to_datetime(data['Date (LT)'])
        data = data.sort_values('datetime')
        data = data.drop_duplicates('datetime')
        data = data.pivot(
            columns='Parameter',
            values='Value',
            index='datetime').reset_index()
        data = data.dropna()
        data_list.append(data)

    return data_list


def read_his_xl(filename):
    # read air4thai historical data
    xl = pd.ExcelFile(filename)
    station_data = pd.DataFrame()

    for sheet_name in xl.sheet_names:
        data = xl.parse(sheet_name, skiprows=[1])

        if len(data) > 0:
            data = parse_1xl_sheet(data)
            station_data = pd.concat([station_data, data], ignore_index=True)
            station_data = convert_pollution_2_number(station_data)

    return station_data.set_index('datetime').dropna(axis=0, how='all')


def isnumber(x):
    # if the data is number
    try:
        float(x)
        return True
    except BaseException:
        return False


def convert_to_float(s):
    """Convert the data in a series to float

    """
    # remove non-numeric data
    s = s[s.apply(isnumber)]
    return s.astype(float)


def convert_to_int(s):
    """Convert the data in a series to int

    """
    # remove non-numeric data
    s = s[s.apply(isnumber)]
    return s.astype(int)


def convert_pollution_2_number(data_df):

    # convert all pollution data to int or float
    pollution_cols = data_df.columns.to_list()
    pollution_cols.remove('datetime')
    # convert data for all pollution column
    for col in pollution_cols:
        s = data_df[col].copy()
        data_df[col] = convert_to_float(s)

    return data_df


def convert_year(data_point):
    # apply to the date column in the data to prepare for making datetime column
    # convert datatype to string
    data_point = str(data_point)

    if len(data_point) == 3:
        data_point = '2000' + '0' + data_point

    elif len(data_point) == 4:
        data_point = '2000' + data_point

    elif len(data_point) == 5:
        data_point = '200' + data_point

    elif len(data_point) == 6:
        if '9' == data_point[0]:
            data_point = '19' + data_point
        else:
            data_point = '20' + data_point

    return data_point


def convert_hour(data_point):
    # apply to the hour column in the data to prepare for making datetime column
    # shift by 1 hour to get rid of 2400
    data_point = int(data_point - 100)
    # convert datatype to string
    data_point = str(data_point)

    if len(data_point) == 3:
        data_point = '0' + data_point

    data_point = data_point[:2]

    # if data_point=='24':
    #    data_point ='00'

    return data_point


def make_datetime_from_xl(data_df):
    # drop nan value
    data_df = data_df[~data_df[['date', 'hour']].isna().any(axis=1)].copy()
    data_df['date'] = data_df['date'].astype(int)
    data_df['hour'] = data_df['hour'].astype(int)
    # preprocess date and hour columns
    data_df['date'] = data_df['date'].apply(convert_year)
    data_df['hour'] = data_df['hour'].apply(convert_hour)
    data_df['datetime'] = data_df['date'] + '-' + data_df['hour']
    data_df['datetime'] = pd.to_datetime(
        data_df['datetime'], format='%Y%m%d-%H')

    # drop old columns
    data_df.drop('date', axis=1, inplace=True)
    data_df.drop('hour', axis=1, inplace=True)

    return data_df


def parse_1xl_sheet(data_df):

    # change column name
    data_df.columns = data_df.columns.str.rstrip()
    data_df.columns = data_df.columns.str.lstrip()
    data_df.columns = data_df.columns.str.replace('ปี/เดือน/วัน', 'date')
    data_df.columns = data_df.columns.str.replace('ชั่วโมง', 'hour')
    to_drops = data_df.columns[data_df.columns.str.contains('Unnamed')]

    # drop nan value
    data_df = data_df[~data_df[['date', 'hour']].isna().any(axis=1)].copy()
    data_df[['date', 'hour']] = data_df[['date', 'hour']].astype(int)
    if len(data_df) > 0:
        # preprocess date and hour columns to create datetime columns
        data_df = make_datetime_from_xl(data_df)
        data_df.drop(to_drops, axis=1, inplace=True)
    else:
        data_df = pd.DataFrame()

    return data_df
