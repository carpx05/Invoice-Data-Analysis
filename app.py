import streamlit as st
import fitz  # PyMuPDF
from fuzzywuzzy import fuzz, process
import pandas as pd
import re
import base64
from PyPDF2 import PdfMerger
import os

st.header('Invoice Data Analysis')
session_state = st.session_state
if 'df' not in session_state:
    session_state.df = None  

if 'result_df' not in session_state:
    session_state.result_df = None

@st.cache_data
def calculate_similarity(address1, address2):
    return fuzz.ratio(address1.lower(), address2.lower())

@st.cache_data
def preprocess_text(text):
    keywords_to_exclude = ["if undelivered, return to:", "If undelivered, return to:", "If undelivered return to:", "Customer Address"]
    text = '\n'.join(line for line in text.split('\n') if all(keyword not in line for keyword in keywords_to_exclude))
    cleaned_text = re.sub(r'[,\n]', ' ', text.lower())
    cleaned_text = ' '.join(set(cleaned_text.split()))
    return cleaned_text

@st.cache_data(show_spinner="Fetching data")
def prepare_df(pdf_file_path, crop_down=120, crop_lr=130, crop_down_inv=50, crop_lr_inv=50):
    doc = fitz.open(pdf_file_path)
    df = pd.DataFrame(columns=["invoice_num", "invoice_date", "customer_address", "page_num"])

    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        text_instances = page.search_for("Customer Address")
        invoice_instances = page.search_for("Invoice No.")

        for text_rect in text_instances:
            x0, y0, x1, y1 = text_rect
            x0_crop = max(x0 - crop_lr, 0)
            x1_crop = min(x1 + crop_lr, page.rect.width)
            y0_crop = max(y0, 0)
            y1_crop = min(y0 + crop_down, page.rect.height)

            page.draw_rect(fitz.Rect(x0_crop, y0_crop, x1_crop, y1_crop), color=(1, 0, 0))

            cropped_area = fitz.Rect(x0_crop, y0_crop, x1_crop, y1_crop)
            cropped_text = page.get_text("text", clip=cropped_area)
            cropped_text = preprocess_text(cropped_text)

        for invoice_instance in invoice_instances:
            x0, y0, x1, y1 = invoice_instance
            x0_crop_inv = max(x0 - crop_lr_inv, 0)
            x1_crop_inv = min(x1 + crop_lr_inv, page.rect.width)
            y0_crop_inv = max(y0, 0)
            y1_crop_inv = min(y0 + crop_down_inv, page.rect.height)

            page.draw_rect(fitz.Rect(x0_crop_inv, y0_crop_inv, x1_crop_inv, y1_crop_inv), color=(1, 0, 0))

            cropped_area_inv = fitz.Rect(x0_crop_inv, y0_crop_inv, x1_crop_inv, y1_crop_inv)
            cropped_text_inv = page.get_text("text", clip=cropped_area_inv)

            invoice_num_match = re.search(r"Invoice No\.\s*(\w+)", cropped_text_inv)
            invoice_num = invoice_num_match.group(1) if invoice_num_match else None

            invoice_date_match = re.search(r"Invoice Date\s*(\d{2}.\d{2}.\d{4})", cropped_text_inv)
            invoice_date = invoice_date_match.group(1) if invoice_date_match else None
            break

        bill_instance = {"invoice_num": invoice_num, "invoice_date": invoice_date, "customer_address": cropped_text,
                         "page_num": page_num}
        df = df._append(bill_instance, ignore_index=True)
    return df

@st.cache_data
def download_link(df, filename='dataframe.csv', text='Download CSV'):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">{text}</a>'
    return href

@st.cache_data(show_spinner="Fetching data")
def find_most_similar_address(query, addresses, threshold=60):
    result = process.extractOne(query, addresses)
    if result[1] >= threshold:
        return result[0]
    else:
        return None

@st.cache_data
def merge_pdfs(uploaded_files):
    merger = PdfMerger()
    for uploaded_file in uploaded_files:
        merger.append(uploaded_file, import_outline=False)
    merged_file_path = "merged_file.pdf"
    with open(merged_file_path, "wb") as output_pdf:
        merger.write(output_pdf)
    merger.close()
    return merged_file_path

@st.cache_data
def save_uploadedfile(uploadedfile):
    if uploadedfile:
        directory = "tempDir"
        if not os.path.exists(directory):
            os.makedirs(directory)
        file_path = os.path.join(directory, uploadedfile.name)
        with open(file_path,"wb") as f:
            f.write(uploadedfile.getbuffer())
        st.success("Saved File:{} to tempDir".format(uploadedfile.name))
        return file_path
    
def save_merged_file(file):
    if file:
        directory = "tempDir"
        if not os.path.exists(directory):
            os.makedirs(directory)
        file_path = os.path.join(directory, file)
        with open(file_path,"wb") as f:
            f.write(file)
        st.success("Saved File:{} to tempDir".format(file))
        return file_path


def main():
    uploaded_file_path = None 
    upload_option = st.selectbox("Choose upload option:", ["Single file", "Multiple files"])
    df = None
    uploaded_file = None
    result_df = pd.DataFrame()

    # File upload based on selected option
    if upload_option == "Single file":
        uploaded_file = st.file_uploader("Upload a single PDF file", type="pdf", accept_multiple_files=False)
        uploaded_file_path = save_uploadedfile(uploaded_file)

    else:
        uploaded_files = st.file_uploader("Upload multiple PDF files", accept_multiple_files=True, type="pdf")
        if uploaded_files:
            uploaded_file = merge_pdfs(uploaded_files)
            print("uploaded_file:",uploaded_file)
            st.success("PDFs merged successfully!")
            uploaded_file_path = uploaded_file
            st.download_button(label="Download Merged PDF", data=open(uploaded_file, "rb").read(), file_name="merged_file.pdf", mime="application/pdf")

    if uploaded_file_path:
        df = prepare_df(uploaded_file_path)

    if st.button('View Analysis'):
        print(df)
        if df is not None:  # Check if df is assigned
        # Proceed with DataFrame operations

            st.write('Here is your DataFrame, Scanned Data')
            st.dataframe(df)
            print("df 1 ready!")

            st.markdown(download_link(df, filename='my_dataframe.csv', text='Download CSV'), unsafe_allow_html=True)

            df['most_similar_address'] = df['customer_address'].apply(lambda x: find_most_similar_address(x, df['customer_address']))
            df_filtered = df.dropna(subset=['most_similar_address'])
            address_counts = df_filtered.groupby('most_similar_address').size().reset_index(name='count')
            result_df = pd.merge(address_counts, df[['most_similar_address', 'page_num']], on='most_similar_address', how='left')
            result_df['page_numbers'] = result_df.groupby('most_similar_address')['page_num'].transform(lambda x: ', '.join(map(str, x)))
            result_df.drop_duplicates(subset=['most_similar_address'], inplace=True)
            result_df = result_df.sort_values(by='count', ascending=False)

            st.write('Here is your DataFrame, Similar Customer Addresses')
            st.dataframe(result_df)
            st.write('page_numbers refer to the page  number of the invoice in the merged pdf. Download Merger PDF to view.')
            print("df 2 ready!")

if __name__ == "__main__":
    main()
