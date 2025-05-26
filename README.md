# Finance Tracker with AI

A simple finance tracking application that uses Flask, Supabase, and Google's Gemini AI to analyze and categorize expenses.

## Features

- Simple expense input interface
- AI-powered expense analysis using Gemini AI
- Automatic categorization into predefined categories
- Modern UI with Tailwind CSS
- Data storage in Supabase

## Setup

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the root directory with the following variables:
   ```
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_anon_key
   GEMINI_API_KEY=your_gemini_api_key
   ```

4. Set up Supabase:
   - Create a new project in Supabase
   - Create a table named `expenses` with the following schema:
     ```sql
     create table expenses (
       id uuid default uuid_generate_v4() primary key,
       description text,
       ai_analysis text,
       created_at timestamp with time zone default timezone('utc'::text, now())
     );
     ```

5. Run the application:
   ```bash
   python app.py
   ```

## Deployment to Vercel

1. Install Vercel CLI:
   ```bash
   npm i -g vercel
   ```

2. Deploy:
   ```bash
   vercel
   ```

3. Add environment variables in Vercel project settings

## Environment Variables

- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Your Supabase project's anon/public key
- `GEMINI_API_KEY`: Your Google AI Gemini API key

## Usage

1. Enter an expense description in the text area (e.g., "Lunch at Subway for $12.99")
2. Click "Analyze & Add Expense"
3. The AI will analyze the input and extract:
   - Expense name
   - Amount
   - Category
4. The analyzed expense will be stored in Supabase 