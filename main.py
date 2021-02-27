import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import yaml
import pandas as pd
import requests
from tabulate import tabulate

vendor_col_name = "vendor"
state_col_name = "state"
appts_available_col_name = "appointment_available"
city_col_name = "city"
address_col_name = "address"
phone_col_name = "phone"
link_col_name = "link"


def fetch_riteaid_vaccine_data(zip, radius, results_df):
    print("Fetching RiteAid vaccine info for the closest 10 stores within a " + radius + " mile radius of " + zip)
    url = "https://www.riteaid.com/services/ext/v2/stores/getStores?" \
          "address=" + zip + "&attrFilter=PREF-112&radius=" + radius
    stores_response = requests.get(url)
    parsed_stores = json.loads(stores_response.text)
    for store_info in parsed_stores["Data"]["stores"]:
        store_num = store_info["storeNumber"]
        store_vaccine_url = "https://www.riteaid.com/services/ext/v2/vaccine/checkSlots?storeNumber=" + str(store_num)
        store_vaccine_response = requests.get(store_vaccine_url)
        parsed_store_vacciene_response = json.loads(store_vaccine_response.text)
        slots_available = parsed_store_vacciene_response["Data"]["slots"]["1"] \
                          or parsed_store_vacciene_response["Data"]["slots"]["2"]
        results_df = results_df.append({
            vendor_col_name: "RiteAid",
            state_col_name: store_info["state"],
            city_col_name: store_info["city"],
            address_col_name: store_info["address"],
            phone_col_name: store_info["fullPhone"],
            appts_available_col_name: slots_available,
        }, ignore_index=True)
    return results_df


def fetch_cvs_vaccine_data(state, results_df):
    print("Fetching CVS vaccine info for " + state)
    url = "https://www.cvs.com/immunizations/covid-19-vaccine.vaccine-status." + state + ".json?vaccineinfo"
    headers = {"referer": "https://www.cvs.com/immunizations/covid-19-vaccine"}
    r = requests.get(url, headers=headers)
    parsedResponse = json.loads(r.text)
    state_info = parsedResponse["responsePayloadData"]["data"][state]
    for city_info in state_info:
        results_df = results_df.append({
            vendor_col_name: "CVS",
            state_col_name: state,
            city_col_name: city_info["city"],
            link_col_name: "https://www.cvs.com/vaccine/intake/store/covid-screener/covid-qns",
            appts_available_col_name: city_info["status"] != "Fully Booked",
        }, ignore_index=True)
    return results_df


def send_email(appointments_df, results_df):
    email_config = get_email_config()
    msg = MIMEMultipart()
    msg['Subject'] = "Covid Vaccine Notifications!"
    msg['From'] = email_config["sender"]["email"]
    html_attmt = """\
    <html>
      <head></head>
      <body>
        <h1>The first table shows places where appointments are available</h1>
        <div>
            {0}
        </div>
        
        <h1>The second table shows organizations that we searched</h1>
        <div>
            {1}
        </div>
      </body>
    </html>
    """.format(appointments_df.to_html(), results_df.to_html())
    mime_text = MIMEText(html_attmt, 'html')
    msg.attach(mime_text)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(email_config["sender"]["email"], email_config["sender"]["password"])
    server.sendmail(msg['From'], email_config["recipients"], msg.as_string())
    server.quit()


def get_email_config():
    with open(r'config.yml') as file:
        email_config = yaml.load(file, Loader=yaml.FullLoader)
        print(email_config)
        return email_config


if __name__ == '__main__':
    print("Starting program...")
    results_df = pd.DataFrame({
        vendor_col_name: pd.Series([], dtype='str'),
        state_col_name: pd.Series([], dtype='str'),
        appts_available_col_name: pd.Series([], dtype='bool'),
        city_col_name: pd.Series([], dtype='str'),
        address_col_name: pd.Series([], dtype='str'),
        phone_col_name: pd.Series([], dtype='str'),
        link_col_name: pd.Series([], dtype='str')})
    print("Fetching data for CVS...")
    results_df = fetch_cvs_vaccine_data("NY", results_df)
    results_df = fetch_cvs_vaccine_data("NJ", results_df)
    print("Fetching data for Rite Aid... ")
    results_df = fetch_riteaid_vaccine_data("07920", "50", results_df)
    print("Printing full dataset...")
    print(tabulate(results_df, headers='keys', tablefmt='psql'))
    print("Printing open appointments dataset...")
    open_appointments_df = results_df[(results_df[appts_available_col_name]==True)]
    print(tabulate(open_appointments_df, headers='keys', tablefmt='psql'))
    # send email if there are open appointments
    # make sure that you have a file called config.yml that has actual senders and recipients configured!
    if not open_appointments_df.empty:
        send_email(open_appointments_df, results_df)

