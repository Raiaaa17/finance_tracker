from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import os
from supabase import create_client
from datetime import datetime, timedelta
from google import genai
from google.genai import types
import json
from collections import defaultdict
import logging

# Configure logging for Vercel
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Constants
EXPENSE_CATEGORIES = [
    "Food & Dining",
    "Transportation",
    "Shopping",
    "Bills & Utilities",
    "Entertainment"
]

# Supabase client factory with connection pooling
def get_db():
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            logger.error("Missing Supabase credentials")
            return None
            
        return create_client(
            supabase_url,
            supabase_key,
            options={
                'timeout': 5,
                'retries': 3,
                'autoRefreshToken': False,
                'persistSession': False
            }
        )
    except Exception as e:
        logger.error(f"Supabase connection error: {str(e)}")
        return None

# Gemini client factory
def get_ai():
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.error("Missing Gemini API key")
            return None
            
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.error(f"Gemini client error: {str(e)}")
        return None

# Database operation wrapper
def db_operation(operation):
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            db = get_db()
            if not db:
                raise Exception("Failed to initialize database connection")
            return operation(db)
        except Exception as e:
            last_error = e
            logger.error(f"Database operation failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                break
    
    raise last_error

# AI operation wrapper
def ai_operation(operation):
    try:
        ai = get_ai()
        if not ai:
            raise Exception("Failed to initialize AI client")
        return operation(ai)
    except Exception as e:
        logger.error(f"AI operation error: {str(e)}")
        raise

# Expense analysis function
analyze_expense_function = {
    "name": "analyze_expense",
    "description": "Analyzes an expense description to extract name, amount, and category.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "A concise name for the expense"},
            "amount": {"type": "number", "description": "The amount of the expense"},
            "category": {
                "type": "string",
                "enum": EXPENSE_CATEGORIES,
                "description": "The category of the expense"
            }
        },
        "required": ["name", "amount", "category"]
    }
}

# Routes
@app.route('/api/health')
def health_check():
    """Health check endpoint for Vercel"""
    return jsonify({'status': 'healthy'}), 200

@app.route('/')
def index():
    """Main dashboard route"""
    try:
        def get_data(db):
            result = db.table('expenses').select('*').order('created_at', desc=True).execute()
            return result.data if result and hasattr(result, 'data') else []
            
        expenses = db_operation(get_data)
        
        # Process expenses for dashboard
        dashboard_data = process_dashboard_data(expenses)
        
        return render_template(
            'index.html',
            categories=EXPENSE_CATEGORIES,
            dashboard=dashboard_data
        )
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return render_template(
            'index.html',
            categories=EXPENSE_CATEGORIES,
            dashboard=get_empty_dashboard(),
            error=str(e)
        )

@app.route('/api/analyze-expense', methods=['POST'])
def analyze_expense():
    """Analyze expense endpoint"""
    try:
        data = request.get_json()
        if not data or 'description' not in data:
            return jsonify({'error': 'Description is required'}), 400
            
        description = data['description'].strip()
        if not description:
            return jsonify({'error': 'Description cannot be empty'}), 400
            
        # Analyze with AI
        def analyze(ai):
            tools = types.Tool(function_declarations=[analyze_expense_function])
            config = types.GenerateContentConfig(tools=[tools])
            
            response = ai.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"Analyze this expense: {description}",
                config=config
            )
            
            if not response.candidates[0].content.parts[0].function_call:
                raise ValueError("AI analysis failed")
                
            return response.candidates[0].content.parts[0].function_call.args
            
        analysis = ai_operation(analyze)
        
        # Store in database
        def store(db):
            expense_data = {
                'description': description,
                'name': analysis['name'],
                'amount': float(analysis['amount']),
                'category': analysis['category'],
                'created_at': datetime.utcnow().isoformat()
            }
            result = db.table('expenses').insert(expense_data).execute()
            return result.data[0] if result and result.data else None
            
        stored_expense = db_operation(store)
        
        return jsonify({
            'success': True,
            'analysis': analysis,
            'data': stored_expense
        })
        
    except Exception as e:
        logger.error(f"Expense analysis error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/expenses')
def get_expenses():
    """Get all expenses endpoint"""
    try:
        def fetch(db):
            result = db.table('expenses').select('*').order('created_at', desc=True).execute()
            return result.data if result and hasattr(result, 'data') else []
            
        expenses = db_operation(fetch)
        return jsonify(expenses)
        
    except Exception as e:
        logger.error(f"Get expenses error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/expense/<expense_id>', methods=['PUT'])
def update_expense(expense_id):
    """Update expense endpoint"""
    try:
        data = request.get_json()
        if not validate_expense_data(data):
            return jsonify({'error': 'Invalid expense data'}), 400
            
        def update(db):
            result = db.table('expenses').update(data).eq('id', expense_id).execute()
            return result.data[0] if result and result.data else None
            
        updated = db_operation(update)
        return jsonify({'success': True, 'data': updated})
        
    except Exception as e:
        logger.error(f"Update expense error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/expense/<expense_id>', methods=['DELETE'])
def delete_expense(expense_id):
    """Delete expense endpoint"""
    try:
        def delete(db):
            result = db.table('expenses').delete().eq('id', expense_id).execute()
            return result.data[0] if result and result.data else None
            
        deleted = db_operation(delete)
        return jsonify({'success': True, 'data': deleted})
        
    except Exception as e:
        logger.error(f"Delete expense error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Helper functions
def process_dashboard_data(expenses):
    """Process expenses for dashboard display"""
    try:
        if not expenses:
            return get_empty_dashboard()
            
        dashboard = {
            'total_expenses': sum(expense['amount'] for expense in expenses),
            'category_totals': defaultdict(float),
            'recent_expenses': expenses[:5],
            'time_series': get_time_series_data(expenses)
        }
        
        # Calculate category totals
        for expense in expenses:
            dashboard['category_totals'][expense['category']] += expense['amount']
            
        # Get top categories
        dashboard['top_categories'] = sorted(
            dashboard['category_totals'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        return dashboard
        
    except Exception as e:
        logger.error(f"Dashboard processing error: {str(e)}")
        return get_empty_dashboard()

def get_time_series_data(expenses):
    """Generate time series data for expenses"""
    try:
        now = datetime.utcnow()
        
        # Initialize time periods
        daily = {(now - timedelta(days=x)).strftime('%Y-%m-%d'): 0 for x in range(30)}
        weekly = {(now - timedelta(weeks=x)).strftime('%Y-W%V'): 0 for x in range(12)}
        monthly = {(now - timedelta(days=30*x)).strftime('%Y-%m'): 0 for x in range(12)}
        
        # Process expenses
        for expense in expenses:
            date = datetime.fromisoformat(expense['created_at'].replace('Z', '+00:00'))
            amount = expense['amount']
            
            day_key = date.strftime('%Y-%m-%d')
            week_key = date.strftime('%Y-W%V')
            month_key = date.strftime('%Y-%m')
            
            if day_key in daily:
                daily[day_key] += amount
            if week_key in weekly:
                weekly[week_key] += amount
            if month_key in monthly:
                monthly[month_key] += amount
                
        return {
            'daily': list(daily.items()),
            'weekly': list(weekly.items()),
            'monthly': list(monthly.items())
        }
        
    except Exception as e:
        logger.error(f"Time series processing error: {str(e)}")
        return {'daily': [], 'weekly': [], 'monthly': []}

def get_empty_dashboard():
    """Return empty dashboard structure"""
    return {
        'total_expenses': 0,
        'category_totals': {},
        'top_categories': [],
        'recent_expenses': [],
        'time_series': {
            'daily': [],
            'weekly': [],
            'monthly': []
        }
    }

def validate_expense_data(data):
    """Validate expense data"""
    try:
        if not all(key in data for key in ['name', 'amount', 'category', 'description']):
            return False
        if not isinstance(data['amount'], (int, float)) or data['amount'] <= 0:
            return False
        if data['category'] not in EXPENSE_CATEGORIES:
            return False
        return True
    except Exception:
        return False

# Vercel configuration
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

# Development server
if __name__ == '__main__':
    app.run(debug=True) 