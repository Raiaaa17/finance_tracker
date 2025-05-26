# Finance Tracker

A modern finance tracking application built with Flask and Supabase, featuring an AI-powered expense analyzer powered by Google's Gemini AI. The application sports a beautiful glass-morphic UI design with a dark theme for optimal viewing experience.

## Features

- 💰 **Expense Tracking**: Easy-to-use interface for adding and managing expenses
- 🤖 **AI Analysis**: Powered by Gemini AI for intelligent expense insights and patterns
- 🎨 **Modern UI**: Glass-morphic design with dark theme
- 📊 **Data Visualization**: Clear visual representation of spending patterns
- 🔐 **Secure Storage**: Data stored securely in Supabase
- 📱 **Responsive Design**: Works seamlessly on both desktop and mobile devices

## Technologies Used

- **Backend**: Flask (Python 3.9)
- **Database**: Supabase
- **AI Integration**: Google Gemini AI
- **Deployment**: Vercel
- **UI Framework**: Custom CSS with glass-morphic design

## Prerequisites

- Python 3.9
- Supabase account and credentials
- Google Gemini AI API key
- Vercel account (for deployment)

## Local Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/Raiaaa17/finance_tracker.git
   cd finance_tracker
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   Create a `.env` file with the following variables:
   ```
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_key
   GEMINI_API_KEY=your_gemini_api_key
   ```

5. Run the development server:
   ```bash
   python app.py
   ```

## Deployment

The application is configured for deployment on Vercel. Key deployment files include:

- `vercel.json`: Configuration for Vercel deployment
- `requirements.txt`: Python dependencies
- `.gitignore`: Git ignore rules

To deploy:

1. Install Vercel CLI:
   ```bash
   npm i -g vercel
   ```

2. Deploy to Vercel:
   ```bash
   vercel --prod
   ```

3. Set up environment variables in Vercel project settings.

## Project Structure

```
finance_tracker/
├── app.py              # Main Flask application
├── static/            # Static assets (CSS, JS)
├── templates/         # HTML templates
├── requirements.txt   # Python dependencies
└── vercel.json       # Vercel configuration
```

## Environment Variables

Required environment variables:

- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Your Supabase project API key
- `GEMINI_API_KEY`: Your Google Gemini AI API key

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 