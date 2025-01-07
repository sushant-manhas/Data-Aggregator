import streamlit as st
import pandas as pd
import io
from parcllabs import ParclLabsClient
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Streamlit Title
st.title("Parcl Real Estate Price Analysis")

# User Input for End Date
end_date = st.date_input("Select the Date", value="2024-12-10")

# API Key Setup (Replace with your method to fetch the key securely)
api_key = st.secrets["PARCL_LABS_API_KEY"]  # Use Streamlit secrets for sensitive data
client = ParclLabsClient(api_key=api_key, limit=12)

def fetch_and_process_data():
    # Fetch Market Data

    # Fetch Market Data
    @st.cache_data
    def fetch_market_data():
        return client.search.markets.retrieve(sort_by='PARCL_EXCHANGE_MARKET', limit=15)

    sales_pricefeed_markets = fetch_market_data()
    sales_pricefeed_parcl_ids = sales_pricefeed_markets['parcl_id'].tolist()

    # Fetch Price Feed Data
    @st.cache_data
    def fetch_price_feed_data(parcl_ids, start_date, end_date):
        return client.price_feed.price_feed.retrieve(
            parcl_ids=parcl_ids,
            start_date=start_date,
            end_date=end_date,
            limit=1000,
            auto_paginate=True
        )

    start_date = (end_date - relativedelta(years=1)).strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    sales_price_feeds = fetch_price_feed_data(sales_pricefeed_parcl_ids, start_date, end_date_str)

    # Merge and Prepare Data
    df = sales_price_feeds.merge(
        sales_pricefeed_markets[['parcl_id', 'name', 'state_abbreviation', 'location_type', 'total_population']],
        on='parcl_id', how='inner'
    ).rename(columns={
        'name': 'friendly_name',
        'state_abbreviation': 'state',
        'location_type': 'boundary_type'
    })

    # Transformation and Calculation
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(by=["friendly_name", "date"])
    latest_date_df = df.loc[df.groupby("friendly_name")["date"].idxmax()]

    # YoY Calculation
    yoy_df = pd.merge(
        latest_date_df.assign(previous_year_date=latest_date_df["date"] - pd.DateOffset(years=1)),
        df,
        left_on=["friendly_name", "previous_year_date"],
        right_on=["friendly_name", "date"],
        suffixes=("", "_prev"),
        how="left"
    )
    yoy_df["YoY Change %"] = ((yoy_df["price_feed"] - yoy_df["price_feed_prev"]) / yoy_df["price_feed_prev"]) * 100

    # YTD Calculation
    yoy_df["start_of_year"] = yoy_df["date"].dt.to_period("Y").dt.start_time
    ytd_df = df[df["date"] == df["date"].dt.to_period("Y").dt.start_time].rename(columns={"price_feed": "start_of_year_price"})
    yoy_ytd_df = pd.merge(yoy_df, ytd_df[["friendly_name", "start_of_year_price"]], on="friendly_name", how="left")
    yoy_ytd_df["YTD Change %"] = ((yoy_ytd_df["price_feed"] - yoy_ytd_df["start_of_year_price"]) / yoy_ytd_df["start_of_year_price"]) * 100

    final_df = yoy_ytd_df.drop_duplicates(subset=["friendly_name"])[["parcl_id", "friendly_name", "state", "boundary_type", "date", "price_feed", "YoY Change %", "YTD Change %"]]
    final_df["YoY Change %"] = final_df["YoY Change %"].round(2)
    final_df["YTD Change %"] = final_df["YTD Change %"].round(2)
    
    # Display Data
    st.write("PriceFeed Data:")
    st.dataframe(final_df)

    # Downloadable Excel File
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Raw PriceFeed Data', index=False)
        final_df.to_excel(writer, sheet_name='Calculations', index=False)
        writer._save()

    st.download_button(
        label="Download Excel File",
        data=buffer,
        file_name="parcl_price_analysis.xlsx",
        mime="application/vnd.ms-excel"
    )
# Button to trigger data fetching and processing
if st.button('Fetch'):
    fetch_and_process_data()
