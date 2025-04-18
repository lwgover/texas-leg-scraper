with companions as (
    SELECT
        bill_id,
        leg_id,
        REPLACE(companion_bill_id,' ','') as companion_bill_id,
        relationship,
        PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S',  first_seen_at) as first_seen_at,
        PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S',  last_seen_at) as last_seen_at
    FROM {{ source('raw_bills', 'companions') }}
),

-- get the most recent timestamp seen for each bill,
bill_most_recent_timestamp as (
    select 
        bill_id,
        leg_id,
        max(last_seen_at) as seen_at_timestamp
    from companions
    group by 1, 2
),

-- remove all the companions that have dropped off
current_companions AS (
    SELECT
        companions.*
    FROM companions
    inner join bill_most_recent_timestamp
        on companions.last_seen_at = bill_most_recent_timestamp.seen_at_timestamp 
        and companions.bill_id = bill_most_recent_timestamp.bill_id
        and companions.leg_id = bill_most_recent_timestamp.leg_id
)


select
    bill_id,
    leg_id,
    companion_bill_id,
    relationship,
    first_seen_at,
    last_seen_at
from current_companions