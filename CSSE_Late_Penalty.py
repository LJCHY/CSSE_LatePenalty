import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
import math
from typing import Dict, Set, Optional, Tuple

# Set page config
st.set_page_config(page_title="Late Penalty Calculator", page_icon="📊", layout="wide")

def parse_datetime(date_str):
    """Parse date strings in various formats"""
    if pd.isna(date_str):
        return None
    
    # Convert to string in case we get a different data type
    date_str = str(date_str).strip()
    
    # List of formats to try
    formats = [
        '%d/%m/%Y %I:%M:%S %p',  # 18/04/2025 11:59:00 PM
        '%d/%m/%Y %H:%M:%S',     # DD/MM/YYYY HH:MM:SS
        '%d/%m/%Y %I:%M %p',     # DD/MM/YYYY HH:MM AM/PM
        '%d/%m/%Y %H:%M',        # DD/MM/YYYY HH:MM
        '%d/%m/%Y',              # DD/MM/YYYY
        '%d-%m-%Y, %H:%M:%S',    # 21-04-2025, 23:59:00
        '%d-%m-%Y %H:%M:%S',     # dd-04-2025 23:59:00
        '%d-%m-%Y, %H:%M',       # dd-04-2025, 23:59
        '%d-%m-%Y %H:%M',        # dd-04-2025 23:59
        '%d-%m-%Y',              # dd-04-2025
        '%Y-%m-%d %H:%M:%S',     # YYYY-MM-DD HH:MM:SS
        '%Y-%m-%d %H:%M',        # YYYY-MM-DD HH:MM
        '%Y-%m-%d',              # YYYY-MM-DD
    ]
    
    # Try each format
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # If the format doesn't include time, set it to 23:59:00
            if fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
                dt = dt.replace(hour=23, minute=59, second=0)
            return dt
        except ValueError:
            continue
    
    # Try pandas parser as last resort
    try:
        return pd.to_datetime(date_str).to_pydatetime()
    except:
        pass
        
    return None

def calculate_late_penalty(hours_late: float, has_special_consideration: bool = False) -> int:
    """
    Calculate late penalty based on hours late and special consideration status
    
    Parameters:
    - hours_late: Number of hours late
    - has_special_consideration: Whether student has extension/UAAP
    
    Returns:
    - Penalty percentage (0-35 or 100)
    """
    if hours_late <= 0:
        return 0
    
    # Regular students
    if not has_special_consideration:
        if hours_late <= 48:
            return 0
        elif hours_late <= 72:
            return 15
        elif hours_late <= 96:
            return 20
        elif hours_late <= 120:
            return 25
        elif hours_late <= 144:
            return 30
        elif hours_late <= 168:
            return 35
        else:
            return 100
    
    # Special consideration students (extension/UAAP)
    else:
        if hours_late <= 24:
            return 5
        elif hours_late <= 48:
            return 10
        elif hours_late <= 72:
            return 15
        elif hours_late <= 96:
            return 20
        elif hours_late <= 120:
            return 25
        elif hours_late <= 144:
            return 30
        elif hours_late <= 168:
            return 35
        else:
            return 100

def process_submission_file(file) -> pd.DataFrame:
    """Process the submission detail file (CSV or Excel)"""
    try:
        # Determine file type and read accordingly
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # Check for required columns
        required_cols = ['Last Edited by: Username', 'Attempt Activity']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            st.error(f"Missing required columns in submission file: {missing_cols}")
            return None
            
        return df
    except Exception as e:
        st.error(f"Error reading submission file: {e}")
        return None

def process_extension_file(file) -> Tuple[Set[str], Dict[str, datetime]]:
    """
    Process the extension/UAAP file
    Returns: (set of student IDs with special consideration, dict of special deadlines)
    """
    special_students = set()
    special_deadlines = {}
    
    try:
        # Determine file type and read accordingly
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # Check for Student ID column
        if 'Student ID' not in df.columns:
            st.error("Missing 'Student ID' column in extension file")
            return special_students, special_deadlines
        
        # Convert Student IDs to strings
        df['Student ID'] = df['Student ID'].astype(str).str.strip()
        
        # Filter out student IDs that start with "00" or have less than 8 digits
        df = df[~df['Student ID'].str.startswith('00')]
        df = df[df['Student ID'].str.len() >= 8]
        
        # Add all remaining students to special consideration set
        special_students = set(df['Student ID'].tolist())
        
        # Check if there's an Extension column for custom deadlines
        if 'Extension' in df.columns:
            for _, row in df.iterrows():
                student_id = row['Student ID']
                extension_date = row['Extension']
                
                if not pd.isna(extension_date):
                    parsed_date = parse_datetime(str(extension_date))
                    if parsed_date:
                        special_deadlines[student_id] = parsed_date
        
        return special_students, special_deadlines
        
    except Exception as e:
        st.error(f"Error reading extension file: {e}")
        return special_students, special_deadlines

def process_data(submission_df: pd.DataFrame, 
                deadline: datetime,
                special_students: Set[str],
                special_deadlines: Dict[str, datetime]) -> pd.DataFrame:
    """Process submission data and calculate late penalties"""
    
    # Filter out rows with missing critical data
    df = submission_df.dropna(subset=['Last Edited by: Username', 'Attempt Activity'])
    
    # Convert Username to string
    df['Last Edited by: Username'] = df['Last Edited by: Username'].astype(str).str.strip()
    
    # Parse submission times
    df['Parsed_Datetime'] = df['Attempt Activity'].apply(parse_datetime)
    df = df.dropna(subset=['Parsed_Datetime'])
    
    # Group by username and find the final submission
    final_submissions = df.sort_values('Parsed_Datetime').groupby('Last Edited by: Username').last().reset_index()
    
    # Calculate hours late and penalties
    results = []
    
    for _, row in final_submissions.iterrows():
        student_id = row['Last Edited by: Username']
        
        # Filter out student IDs that start with "00" or have less than 8 digits
        if student_id.startswith('00') or len(student_id) < 8:
            continue
            
        submission_time = row['Parsed_Datetime']
        
        # Determine deadline for this student
        if student_id in special_deadlines:
            student_deadline = special_deadlines[student_id]
        else:
            student_deadline = deadline
        
        # Calculate hours late
        if submission_time and student_deadline:
            hours_late = (submission_time - student_deadline).total_seconds() / 3600
            hours_late = max(0, hours_late)  # Can't be negative
        else:
            hours_late = 0
        
        # Check if student has special consideration
        has_special = student_id in special_students
        
        # Calculate penalty
        penalty = calculate_late_penalty(hours_late, has_special)
        
        # Create result record
        result = {
            'Student_ID': student_id,
            'Student_Name': row.get('Last Edited by: Name', 'Unknown'),
            'Submission_Time': row['Attempt Activity'],
            'Hours_Late': round(hours_late, 2),
            'Late_Penalty': f'{penalty}%',
            'Deadline_Used': student_deadline.strftime('%d/%m/%Y %H:%M:%S'),
            'Special_Consideration': 'Yes' if has_special else 'No'
        }
        
        results.append(result)
    
    return pd.DataFrame(results)

# Streamlit UI
st.title("📊 Late Penalty Calculator")
st.markdown("Calculate late penalties for student submissions with special consideration support")

# Instructions
with st.expander("ℹ️ Instructions (READ ME!)"):
    st.markdown("""
    ### How to use this application:
    
    1. **Upload Files:**
       - **File 1 (Submission Details):** Must contain columns 'Last Edited by: Username' and 'Attempt Activity' (The file can be downloaded on LMS (Grade History))
       - **File 2 (Extension/UAAP):** Must contain 'Student ID' column and 'Extension' column for custom deadlines (new deadline for UAAP or Extensions, the format is '%d/%m/%Y %H:%M:%S' (like "06/07/2025 23:59:00"))
    
    2. **Select Due Date:** Choose the assignment due date. Time is automatically set to 23:59:00
    
    3. **Late Penalty Rules:**
       - **Students without Extension/UAAP:** 
         - 0-48 hours late: 0% penalty
         - >48-72 hours late: 15% penalty
         - >72-96 hours late: 20% penalty
         - >96-120 hours late: 25% penalty
         - >120-144 hours late: 30% penalty
         - >144-168 hours late: 35% penalty
         - >168 hours (7 days): 100% penalty
       - **Students with Extension/UAAP:**
         - >0-24 hours late: 5% penalty
         - >24-48 hours late: 10% penalty
         - >48-72 hours late: 15% penalty
         - >72-96 hours late: 20% penalty
         - >96-120 hours late: 25% penalty
         - >120-144 hours late: 30% penalty
         - >144-168 hours late: 35% penalty
         - >168 hours (7 days): 100% penalty
    
    4. **Click Calculate** to process the data and view results
    
    5. **Download Results** as CSV for further analysis
    """)

# Create two columns for file uploads
col1, col2 = st.columns(2)

with col1:
    st.subheader("📄 File 1: Submission Details")
    submission_file = st.file_uploader(
        "Upload submission detail file (CSV or Excel)",
        type=['csv', 'xlsx', 'xls'],
        key="submission"
    )
    
with col2:
    st.subheader("📋 File 2: Extension/UAAP")
    extension_file = st.file_uploader(
        "Upload extension/UAAP file (CSV or Excel)",
        type=['csv', 'xlsx', 'xls'],
        key="extension"
    )

# Date selector
st.subheader("📅 Due Date Selection")
due_date = st.date_input(
    "Select due date (time will be set to 23:59:00)",
    value=datetime.today().date()
)

# Convert date to datetime with 23:59:00
deadline = datetime.combine(due_date, datetime.min.time().replace(hour=23, minute=59, second=0))
st.info(f"Deadline set to: {deadline.strftime('%d/%m/%Y %H:%M:%S')}")

# Process button
if st.button("🚀 Calculate Late Penalties", type="primary"):
    if not submission_file:
        st.error("Please upload a submission detail file")
    else:
        # Process submission file
        submission_df = process_submission_file(submission_file)
        
        if submission_df is not None:
            # Process extension file if provided
            special_students = set()
            special_deadlines = {}
            
            if extension_file:
                special_students, special_deadlines = process_extension_file(extension_file)
                st.success(f"Found {len(special_students)} students with special consideration")
            
            # Process data
            results_df = process_data(submission_df, deadline, special_students, special_deadlines)
            
            # Display results
            st.subheader("📊 Results")
            
            # Summary statistics
            col1, col2, col3, col4 = st.columns(4)
            
            total_students = len(results_df)
            on_time = len(results_df[results_df['Late_Penalty'] == '0%'])
            late = total_students - on_time
            special_count = len(results_df[results_df['Special_Consideration'] == 'Yes'])
            
            with col1:
                st.metric("Total Students", total_students)
            with col2:
                st.metric("On Time", on_time)
            with col3:
                st.metric("Late", late)
            with col4:
                st.metric("Special Consideration", special_count)
            
            # Display data table
            st.dataframe(results_df, use_container_width=True)
            
            # Download button
            csv = results_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Results as CSV",
                data=csv,
                file_name=f"late_penalties_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
            
            # Penalty distribution
            st.subheader("📈 Penalty Distribution")
            penalty_counts = results_df['Late_Penalty'].value_counts().sort_index()
            st.bar_chart(penalty_counts)

# Footer
st.markdown("---")
st.markdown("Late Penalty Calculator v1.0 | Created with Streamlit")