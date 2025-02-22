import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import io
import zipfile
from datetime import datetime
import httpx

# Supabase Configuration
SUPABASE_URL = "https://yetmtzyyztirghaxnccp.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
CERTIFICATE_GENERATOR_PASSWORD = st.secrets["CERTIFICATE_GENERATOR_PASSWORD"]

# Set page config first
st.set_page_config(page_title="Certificate Generator", layout="wide")

# Authentication
st.title("Certificate Generator App")
password = st.text_input("Enter Password:", type="password")
if password != CERTIFICATE_GENERATOR_PASSWORD:
    st.error("Incorrect password. Access denied.")
    st.stop()

# Certificate template mapping
TEMPLATE_MAP = {
    "Employee of the Month": "001.pdf",
    "Student of the Month": "002.pdf"
}

# Download CSV template button
template_csv_url = "https://raw.githubusercontent.com/bayr-harrison/ARX_Certificate_Generator/blob/main/certificate_generator_template.csv"
with open("certificate_generator_template.csv", "wb") as file:
    file.write(httpx.get(template_csv_url).content)
with open("certificate_generator_template.csv", "rb") as file:
    st.download_button(
        label="📥 Download CSV Template",
        data=file,
        file_name="certificate_generator_template.csv",
        mime="text/csv"
    )

def insert_certificate(iatc_id, name, issue_date, cert_type, cert_url):
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "iatc_id": iatc_id,
        "name": name,
        "issue_date": issue_date,
        "cert_type": cert_type,
        "cert_url": cert_url
    }
    response = httpx.post(f"{SUPABASE_URL}/rest/v1/certificates", json=data, headers=headers)
    if response.status_code != 201:
        st.error(f"Error inserting into database: {response.text}")

def upload_certificate_to_supabase(pdf_bytes, file_name):
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/pdf"
    }
    upload_url = f"{SUPABASE_URL}/storage/v1/object/certificates/issued_certificates/{file_name}"
    response = httpx.put(upload_url, content=pdf_bytes, headers=headers)
    if response.status_code == 200:
        return upload_url
    else:
        st.error(f"Failed to upload {file_name}: {response.text}")
        return None

tabs = st.tabs(["Certificate Generator", "Certificate Log"])

with tabs[0]:  # Certificate Generator Page
    st.title("Certificate Generator")
    cert_type = st.selectbox("Select Certificate Type", list(TEMPLATE_MAP.keys()))
    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])

    if uploaded_file and st.button("Generate Certificates"):
        df = pd.read_csv(uploaded_file)
        zip_buffer = io.BytesIO()
        zipf = zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED)

        cert_links = []

        for index, row in df.iterrows():
            iatc_id = row['iatc_id']
            name = row['name']
            issue_date = datetime.strptime(row['issue_date'], "%d/%m/%Y").strftime("%Y-%m-%d")
            template_path = f"{SUPABASE_URL}/storage/v1/object/certificates/templates/{TEMPLATE_MAP[cert_type]}"
            file_name = f"{iatc_id}_{TEMPLATE_MAP[cert_type][:3]}_{issue_date}.pdf"
            cert_url = f"{SUPABASE_URL}/storage/v1/object/certificates/issued_certificates/{file_name}"

            # Load template
            response = httpx.get(template_path)
            doc = fitz.open(stream=response.content, filetype="pdf")
            page = doc[0]

            # Define fancy text placement
            name_id_text = f"{name} ({iatc_id})"
            text_font = "Times-Bold"
            text_size = 50
            date_font_size = 30

            # Calculate text width for centering
            text_width = fitz.get_text_length(name_id_text, fontsize=text_size, fontname=text_font)
            date_width = fitz.get_text_length(issue_date, fontsize=date_font_size, fontname=text_font)

            # Center text horizontally
            x_center_name = (page.rect.width - text_width) / 2
            x_center_date = (page.rect.width - date_width) / 2

            page.insert_text((x_center_name, 300), name_id_text, fontsize=text_size, fontname=text_font, color=(0, 0, 0))
            page.insert_text((x_center_date, 380), issue_date, fontsize=date_font_size, fontname=text_font, color=(0, 0, 0))

            pdf_buffer = io.BytesIO()
            doc.save(pdf_buffer)
            pdf_buffer.seek(0)

            # Upload certificate to Supabase
            uploaded_cert_url = upload_certificate_to_supabase(pdf_buffer.getvalue(), file_name)
            if uploaded_cert_url:
                insert_certificate(iatc_id, name, issue_date, cert_type, uploaded_cert_url)

            # Save to zip file
            zipf.writestr(file_name, pdf_buffer.getvalue())
            cert_links.append(uploaded_cert_url)

        zipf.close()
        zip_buffer.seek(0)
        st.download_button("Download Certificates (ZIP)", zip_buffer, file_name="certificates.zip", mime="application/zip")

        st.success("Certificates generated and uploaded successfully!")

with tabs[1]:  # Certificate Log Page
    st.title("Certificate Log")
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
    }
    response = httpx.get(f"{SUPABASE_URL}/rest/v1/certificates", headers=headers)

    if response.status_code == 200:
        data = response.json()
        df_log = pd.DataFrame(data)

        if df_log.empty:
            st.warning("No records found in the database.")
        else:
            st.dataframe(df_log, use_container_width=True)
            filter_columns = st.multiselect("Filter by columns:", df_log.columns)
            if filter_columns:
                for col in filter_columns:
                    unique_values = df_log[col].unique()
                    selected_values = st.multiselect(f"Select {col}", unique_values)
                    if selected_values:
                        df_log = df_log[df_log[col].isin(selected_values)]
                st.dataframe(df_log, use_container_width=True)
    else:
        st.error(f"Failed to fetch certificate log: {response.text}")
