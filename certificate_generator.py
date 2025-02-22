import streamlit as st
import requests
import pandas as pd
import fitz  # PyMuPDF
import io
import zipfile
from datetime import datetime
import httpx
import qrcode
from PIL import Image

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

# Add download link for Coversheet Tool
cert_gen_template_url = "https://raw.githubusercontent.com/bayr-harrison/ARX_Certificate_Generator/main/certificate_generator_template.xlsx"
st.markdown(
    f'<a href="{cert_gen_template_url}" download><button style="background-color: #4CAF50; border: none; color: white; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 10px 2px; cursor: pointer; border-radius: 5px;">Download Certificate Generator Tool</button></a>',
    unsafe_allow_html=True
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
            try:
                issue_date = datetime.strptime(str(row['issue_date']).strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
            except ValueError:
                continue  # Skip rows with invalid dates

            iatc_id = row['iatc_id']
            name = row['name']
            template_path = f"{SUPABASE_URL}/storage/v1/object/certificates/templates/{TEMPLATE_MAP[cert_type]}"
            file_name = f"{iatc_id}_{TEMPLATE_MAP[cert_type][:3]}_{issue_date}.pdf"
            cert_url = f"{SUPABASE_URL}/storage/v1/object/certificates/issued_certificates/{file_name}"

            # Load template
            response = httpx.get(template_path)
            doc = fitz.open(stream=response.content, filetype="pdf")
            page = doc[0]

            # Generate QR Code with cert_url
            qr = qrcode.make(cert_url)
            qr_img = qr.get_image()

            # Convert QR Code to Bytes
            qr_buffer = io.BytesIO()
            qr_img.save(qr_buffer, format="PNG")
            qr_buffer.seek(0)

            # Insert QR Code Image - moved down and slightly to the right
            qr_x = 80  # Increased from 50 to move right
            qr_y = 140  # Increased from 35 to move down
            qr_img_fit = fitz.Pixmap(qr_buffer)
            page.insert_image(fitz.Rect(qr_x, qr_y, qr_x + 100, qr_y + 100), pixmap=qr_img_fit)

            # Define text placement
            name_id_text = f"{name} ({iatc_id})"
            text_font = "Times-Bold"
            text_size = 30
            date_font_size = 20

            # Center text horizontally
            text_width = fitz.get_text_length(name_id_text, fontsize=text_size, fontname=text_font)
            date_width = fitz.get_text_length(issue_date, fontsize=date_font_size, fontname=text_font)

            x_center_name = (page.rect.width - text_width) / 2
            x_center_date = (page.rect.width - date_width) / 2

            # Insert text into PDF
            page.insert_text((x_center_name, 300), name_id_text, fontsize=text_size, fontname=text_font, color=(0, 0, 0))
            page.insert_text((x_center_date, 380), issue_date, fontsize=date_font_size, fontname=text_font, color=(0, 0, 0))  # Moved up slightly

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
            # Convert cert_url column to clickable icons
            df_log["cert_url"] = df_log["cert_url"].apply(
                lambda x: f'<a href="{x}" target="_blank"><img src="https://img.icons8.com/ios-filled/20/000000/external-link.png"/></a>'
            )
            st.write(df_log.to_html(escape=False, index=False), unsafe_allow_html=True)

            # Add filtering
            filter_columns = st.multiselect("Filter by columns:", df_log.columns)
            if filter_columns:
                for col in filter_columns:
                    unique_values = df_log[col].unique()
                    selected_values = st.multiselect(f"Select {col}", unique_values)
                    if selected_values:
                        df_log = df_log[df_log[col].isin(selected_values)]
                st.write(df_log.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.error(f"Failed to fetch certificate log: {response.text}")
