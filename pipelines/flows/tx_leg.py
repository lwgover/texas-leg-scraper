import sys
import yaml
import datetime
import logging
import google.auth

from prefect import flow, task
from utils import FtpConnection, dataframe_to_bigquery, log_bq_load, get_current_table_data, determine_git_environment, read_gsheets_to_df, upload_google_sheets, get_secret
from extract_functions import *
from pull_legiscan_data import legiscan_to_bigquery

################################################################################
# CONFIGURATION
################################################################################

CONFIG_PATH = 'config.yaml'
GSHEETS_CONFIG_PATH = 'gsheets_runs.yaml'
LOG_PATH = 'tx-leg.log'
OUT_DATASET_NAME = 'tx_leg_raw_bills'
PROJECT_ID = get_secret(secret_id='GCP_PROJECT_ID')
ENV = determine_git_environment()

logger = logging.getLogger(__name__)
logging.basicConfig(filename=LOG_PATH, level=logging.DEBUG)


################################################################################
# Google Sheets
################################################################################

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def download_google_sheet(google_sheets_id, worksheet_name, output_table_id):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process {output_table_id} data")
    google_sheets_df = read_gsheets_to_df(google_sheets_id, worksheet_name)
    dataframe_to_bigquery(google_sheets_df, PROJECT_ID, OUT_DATASET_NAME, output_table_id, ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, output_table_id, ENV, 'drop', sys.getsizeof(google_sheets_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- {output_table_id} data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def download_google_sheets(gsheets_config_path):
    with open(gsheets_config_path, 'r') as file:
        gsheets_config = yaml.safe_load(file)

    for download in gsheets_config['downloads']:
        download_google_sheet(download['google_sheets_id'], download['worksheet_name'], download['table_id'])

################################################################################
# DATA PIPELINE
################################################################################

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def bills(raw_bills_df):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process bills data")
    bills_df = get_bills_data(raw_bills_df)

    curr_time = pd.Timestamp.now().floor('min')
    bills_df['last_seen_at'] = curr_time
    bills_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(bills_df, PROJECT_ID, OUT_DATASET_NAME, 'bills', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'bills', ENV, 'drop', sys.getsizeof(bills_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Bills data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def actions(raw_bills_df):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process actions data")
    actions_df = get_actions_data(raw_bills_df)

    curr_time = pd.Timestamp.now().floor('min')
    actions_df['last_seen_at'] = curr_time
    actions_df['first_seen_at'] = curr_time

    actions_df = actions_df.drop_duplicates()
    dataframe_to_bigquery(actions_df, PROJECT_ID, OUT_DATASET_NAME, 'actions', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'actions', ENV, 'drop', sys.getsizeof(actions_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Actions data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def authors(raw_bills_df):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process authors data")
    authors_df = get_authors_data(raw_bills_df)
    
    curr_time = pd.Timestamp.now().floor('min')
    authors_df['last_seen_at'] = curr_time
    authors_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(authors_df, PROJECT_ID, OUT_DATASET_NAME, 'authors', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'authors', ENV, 'drop', sys.getsizeof(authors_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Authors data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def bill_stages(raw_bills_df, config):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process bill stages data")
    bill_stages_df = get_bill_stages(config['sources']['html']['bill_stages'], raw_bills_df)
    
    curr_time = pd.Timestamp.now().floor('min')
    bill_stages_df['last_seen_at'] = curr_time
    bill_stages_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(bill_stages_df, PROJECT_ID, OUT_DATASET_NAME, 'bill_stages', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'bill_stages', ENV, 'drop', sys.getsizeof(bill_stages_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Bill stages data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def bill_texts(ftp_conn):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process bill texts data")
    first_seen_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    bill_texts_df = get_bill_texts(ftp_conn, OUT_DATASET_NAME, ENV)
    bill_texts_df['seen_at'] = first_seen_at

    dataframe_to_bigquery(bill_texts_df, PROJECT_ID, OUT_DATASET_NAME, 'bill_texts', ENV, 'append')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'bill_texts', ENV, 'append', sys.getsizeof(bill_texts_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Bill texts data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def committee_status(raw_bills_df):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process committee status data")
    committees_df = get_committee_status_data(raw_bills_df)
    
    curr_time = pd.Timestamp.now().floor('min')
    committees_df['last_seen_at'] = curr_time
    committees_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(committees_df, PROJECT_ID, OUT_DATASET_NAME, 'committee_status', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'committees', ENV, 'drop', sys.getsizeof(committees_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Committees data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def committee_hearing_videos(config):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process committee hearing videos data")
    committee_hearing_videos_df = get_committee_hearing_videos_data(config)
    
    curr_time = pd.Timestamp.now().floor('min')
    committee_hearing_videos_df['last_seen_at'] = curr_time
    committee_hearing_videos_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(committee_hearing_videos_df, PROJECT_ID, OUT_DATASET_NAME, 'committee_hearing_videos', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'committee_hearing_videos', ENV, 'drop', sys.getsizeof(committee_hearing_videos_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Committee hearing videos data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def committee_meetings(config):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process committee meetings data")
    committee_meetings_df = get_committee_meetings_data(config)
    
    curr_time = pd.Timestamp.now().floor('min')
    committee_meetings_df['last_seen_at'] = curr_time
    committee_meetings_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(committee_meetings_df, PROJECT_ID, OUT_DATASET_NAME, 'committee_meetings', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'committee_meetings', ENV, 'drop', sys.getsizeof(committee_meetings_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Committee meetings data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def committee_meeting_bills(config):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process committee meeting bills data")
    committee_meeting_bills_df = get_committee_meeting_bills_data(config)
    
    curr_time = pd.Timestamp.now().floor('min')
    committee_meeting_bills_df['last_seen_at'] = curr_time
    committee_meeting_bills_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(committee_meeting_bills_df, PROJECT_ID, OUT_DATASET_NAME, 'committee_meeting_bills', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'committee_meeting_bills', ENV, 'drop', sys.getsizeof(committee_meeting_bills_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Committee meeting bills data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def committee_meetings_links(config):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process committee meetings links data")
    committee_meetings_df = get_committee_meetings_data(config)
    
    curr_time = pd.Timestamp.now().floor('min')
    committee_meetings_df['last_seen_at'] = curr_time
    committee_meetings_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(committee_meetings_df, PROJECT_ID, OUT_DATASET_NAME, 'committee_meetings_links', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'committee_meetings_links', ENV, 'drop', sys.getsizeof(committee_meetings_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Committee meetings links data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def companions(raw_bills_df):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process companions data")
    companions_df = get_companions_data(raw_bills_df)

    curr_time = pd.Timestamp.now().floor('min')
    companions_df['last_seen_at'] = curr_time
    companions_df['first_seen_at'] = curr_time

    dataframe_to_bigquery(companions_df, PROJECT_ID, OUT_DATASET_NAME, 'companions', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'companions', ENV, 'drop', sys.getsizeof(companions_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Companions data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def complete_bills_list(raw_bills_df):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process complete bills list data")
    complete_bills_list_df = get_complete_bills_list(raw_bills_df)
    
    curr_time = pd.Timestamp.now().floor('min')
    complete_bills_list_df['last_seen_at'] = curr_time
    complete_bills_list_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(complete_bills_list_df, PROJECT_ID, OUT_DATASET_NAME, 'complete_bills_list', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'complete_bills_list', ENV, 'drop', sys.getsizeof(complete_bills_list_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Complete bills list data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def links(raw_bills_df, config):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process links data")
    links_df = get_links_data(raw_bills_df,config)
    
    curr_time = pd.Timestamp.now().floor('min')
    links_df['last_seen_at'] = curr_time
    links_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(links_df, PROJECT_ID, OUT_DATASET_NAME, 'links', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'links', ENV, 'drop', sys.getsizeof(links_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Links data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def sponsors(raw_bills_df):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process sponsors data")
    sponsors_df = get_sponsors_data(raw_bills_df)
    
    curr_time = pd.Timestamp.now().floor('min')
    sponsors_df['last_seen_at'] = curr_time
    sponsors_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(sponsors_df, PROJECT_ID, OUT_DATASET_NAME, 'sponsors', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'sponsors', ENV, 'drop', sys.getsizeof(sponsors_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Sponsors data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def subjects(raw_bills_df):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process subjects data")
    subjects_df = get_subjects_data(raw_bills_df)
    
    curr_time = pd.Timestamp.now().floor('min')
    subjects_df['last_seen_at'] = curr_time
    subjects_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(subjects_df, PROJECT_ID, OUT_DATASET_NAME, 'subjects', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'subjects', ENV, 'drop', sys.getsizeof(subjects_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Subjects data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def rss_feeds(config):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process RSS feeds data")
    rss_df = get_rss_data(config)
    
    curr_time = pd.Timestamp.now().floor('min')
    rss_df['last_seen_at'] = curr_time
    rss_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(rss_df, PROJECT_ID, OUT_DATASET_NAME, 'rss_feeds', ENV, 'append')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'rss_feeds', ENV, sys.getsizeof(rss_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- RSS feeds data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def upcoming_committee_meetings(config):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process upcoming committee meetings data")
    upcoming_meetings_df = get_upcoming_committee_meetings(config)
    upcoming_meetings_df['seen_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    dataframe_to_bigquery(upcoming_meetings_df, PROJECT_ID, OUT_DATASET_NAME, 'upcoming_committee_meetings', ENV, 'append')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'upcoming_committee_meetings', ENV, 'append', sys.getsizeof(upcoming_meetings_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Upcoming committee meetings data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def upcoming_committee_meeting_bills(config):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process upcoming committee meeting bills data")
    upcoming_meeting_bills_df = get_upcoming_committee_meeting_bills(config)
    upcoming_meeting_bills_df['seen_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    dataframe_to_bigquery(upcoming_meeting_bills_df, PROJECT_ID, OUT_DATASET_NAME, 'upcoming_committee_meeting_bills', ENV, 'append')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'upcoming_committee_meeting_bills', ENV, 'append', sys.getsizeof(upcoming_meeting_bills_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Upcoming committee meeting bills data processing complete")

@task(retries=0, retry_delay_seconds=10, log_prints=True, cache_policy=NO_CACHE)
def versions(raw_bills_df):
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting to process versions data")
    versions_df = get_versions_data(raw_bills_df)
    
    curr_time = pd.Timestamp.now().floor('min')
    versions_df['last_seen_at'] = curr_time
    versions_df['first_seen_at'] = curr_time
    
    dataframe_to_bigquery(versions_df, PROJECT_ID, OUT_DATASET_NAME, 'versions', ENV, 'drop')
    log_bq_load(PROJECT_ID, OUT_DATASET_NAME, 'versions', ENV, 'drop', sys.getsizeof(versions_df))
    logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Versions data processing complete")

@task(retries=1, retry_delay_seconds=1, log_prints=True, cache_policy=NO_CACHE)
def legiscan(config):
    legiscan_to_bigquery(config, PROJECT_ID, 'tx_leg_raw_bills', ENV)

################################################################################
# MAIN
################################################################################

@flow(name="Texas Leg Pipeline", log_prints=True)
def tx_leg_pipeline(env=None):

    logger = logging.getLogger(__name__)
    print('USING ENV: ', ENV)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    try:
        conn = FtpConnection(config['sources']['ftp']['host'])
    except Exception as e:
        logger.error(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Failed to connect to FTP: {e}")
        raise e

    base_path = config['sources']['ftp']['base_path']
    leg_session = config['info']['LegSess']

    # first get the dataframes without raw_bills_df
    committee_hearing_videos(config)
    committee_meeting_bills(config)
    committee_meetings(config)
    upcoming_committee_meetings(config)
    upcoming_committee_meeting_bills(config)

    try:
        logger.info(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Starting raw bills data extraction")
        raw_bills_df = get_raw_bills_data(base_path, leg_session, conn)
        logger.info("Raw bills data extraction complete")
    except Exception as e:
        logger.error(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Failed to get raw bills data: {e}")
        raise e

    # curr_rss_df =  get_current_table_data(PROJECT_ID, OUT_DATASET_NAME, 'rss_feeds', ENV)

    actions(raw_bills_df)
    authors(raw_bills_df)
    bills(raw_bills_df)
    committee_status(raw_bills_df)
    companions(raw_bills_df)
    complete_bills_list(raw_bills_df)
    links(raw_bills_df, config)
    subjects(raw_bills_df)
    versions(raw_bills_df)

    bill_stages(raw_bills_df, config)
    # bill_texts(conn)

    legiscan(config)

    download_google_sheets(GSHEETS_CONFIG_PATH)
    # rss_feeds(config, curr_rss_df),

    upload_google_sheets(GSHEETS_CONFIG_PATH, CONFIG_PATH, ENV)