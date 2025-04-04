SELECT
    bill_id,
    leg_id,
        case chamber
        when 'house' then 'House' 
        when 'senate' then 'Senate'
        when 'joint' then 'Joint'
        else 'Unknown' end as chamber,
    REPLACE(name, '&', 'and') as name,
    -- subcommittee_name,
    status,
    -- subcommittee_status,
    aye_votes,
    nay_votes,
    present_votes, 
    absent_votes,
    first_seen_at,
    last_seen_at
FROM {{ source('raw_bills', 'committees') }}
where name != ''