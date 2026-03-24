-- Taiwan Stock Monitoring Robot Database Schema
-- Target: PostgreSQL 15+

-- Create database if not exists (handled by docker-compose)
-- CREATE DATABASE tw_stock;

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Stocks master table
CREATE TABLE stocks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(10) NOT NULL UNIQUE, -- 股票代號
    name VARCHAR(100) NOT NULL,         -- 股票名稱
    market VARCHAR(10) NOT NULL,        -- 市場 (TSE, OTC)
    industry VARCHAR(50),               -- 產業別
    is_active BOOLEAN DEFAULT TRUE,     -- 是否啟用監控
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Stock price history (OHLCV data)
CREATE TABLE stock_prices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    open_price DECIMAL(10,2) NOT NULL,
    high_price DECIMAL(10,2) NOT NULL,
    low_price DECIMAL(10,2) NOT NULL,
    close_price DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    turnover DECIMAL(15,2),             -- 成交金額
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(stock_id, date)
);

-- Real-time stock data (latest tick)
CREATE TABLE stock_realtime (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
    current_price DECIMAL(10,2) NOT NULL,
    change_amount DECIMAL(10,2) NOT NULL,
    change_percent DECIMAL(5,2) NOT NULL,
    volume BIGINT NOT NULL,
    bid_price DECIMAL(10,2),
    ask_price DECIMAL(10,2),
    bid_volume INTEGER,
    ask_volume INTEGER,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(stock_id)
);

-- Technical indicators
CREATE TABLE technical_indicators (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    ma5 DECIMAL(10,2),                  -- 5日均線
    ma10 DECIMAL(10,2),                 -- 10日均線
    ma20 DECIMAL(10,2),                 -- 20日均線
    ma60 DECIMAL(10,2),                 -- 60日均線
    rsi14 DECIMAL(5,2),                 -- 14日RSI
    macd DECIMAL(10,4),                 -- MACD
    macd_signal DECIMAL(10,4),          -- MACD信號線
    macd_histogram DECIMAL(10,4),       -- MACD柱狀圖
    bb_upper DECIMAL(10,2),             -- 布林通道上軌
    bb_middle DECIMAL(10,2),            -- 布林通道中軌
    bb_lower DECIMAL(10,2),             -- 布林通道下軌
    volume_ma20 BIGINT,                 -- 20日均量
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(stock_id, date)
);

-- Signal alerts
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
    alert_type VARCHAR(20) NOT NULL,    -- BUY, SELL, WATCH
    signal_name VARCHAR(50) NOT NULL,   -- 訊號名稱
    price DECIMAL(10,2) NOT NULL,
    description TEXT,
    is_sent BOOLEAN DEFAULT FALSE,      -- 是否已發送通知
    triggered_at TIMESTAMP WITH TIME ZONE NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User portfolios
CREATE TABLE portfolios (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(50) NOT NULL,      -- Telegram user ID
    name VARCHAR(100) DEFAULT 'Default Portfolio',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, name)
);

-- Portfolio holdings
CREATE TABLE portfolio_holdings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL,          -- 持股數量（以股為單位）
    avg_cost DECIMAL(10,2) NOT NULL,    -- 平均成本
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(portfolio_id, stock_id)
);

-- Transaction history
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
    transaction_type VARCHAR(10) NOT NULL, -- BUY, SELL
    quantity INTEGER NOT NULL,          -- 交易數量（以股為單位）
    price DECIMAL(10,2) NOT NULL,       -- 交易價格
    fee DECIMAL(10,2) DEFAULT 0,        -- 手續費
    tax DECIMAL(10,2) DEFAULT 0,        -- 稅費
    total_amount DECIMAL(15,2) NOT NULL, -- 總金額
    transaction_date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Telegram user settings
CREATE TABLE telegram_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    telegram_id VARCHAR(50) NOT NULL UNIQUE,
    username VARCHAR(100),
    first_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    alert_enabled BOOLEAN DEFAULT TRUE,
    alert_types TEXT[] DEFAULT ARRAY['BUY', 'SELL'], -- 接收的警報類型
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Watchlist
CREATE TABLE watchlists (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(50) NOT NULL REFERENCES telegram_users(telegram_id),
    stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, stock_id)
);

-- System logs
CREATE TABLE system_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    level VARCHAR(10) NOT NULL,         -- DEBUG, INFO, WARNING, ERROR, CRITICAL
    module VARCHAR(50) NOT NULL,        -- api, scanner, telegram, etc.
    message TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- API rate limiting
CREATE TABLE api_rate_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    api_name VARCHAR(50) NOT NULL,      -- fubon_api, telegram_api
    endpoint VARCHAR(100),
    request_count INTEGER DEFAULT 0,
    window_start TIMESTAMP WITH TIME ZONE NOT NULL,
    window_duration_minutes INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(api_name, endpoint, window_start)
);

-- Create indexes for better performance
CREATE INDEX idx_stocks_symbol ON stocks(symbol);
CREATE INDEX idx_stocks_market ON stocks(market);
CREATE INDEX idx_stock_prices_date ON stock_prices(date);
CREATE INDEX idx_stock_prices_stock_date ON stock_prices(stock_id, date);
CREATE INDEX idx_stock_realtime_timestamp ON stock_realtime(timestamp);
CREATE INDEX idx_technical_indicators_stock_date ON technical_indicators(stock_id, date);
CREATE INDEX idx_alerts_triggered_at ON alerts(triggered_at);
CREATE INDEX idx_alerts_is_sent ON alerts(is_sent);
CREATE INDEX idx_alerts_stock_type ON alerts(stock_id, alert_type);
CREATE INDEX idx_transactions_date ON transactions(transaction_date);
CREATE INDEX idx_transactions_portfolio ON transactions(portfolio_id);
CREATE INDEX idx_system_logs_created_at ON system_logs(created_at);
CREATE INDEX idx_system_logs_level ON system_logs(level);
CREATE INDEX idx_api_rate_limits_window ON api_rate_limits(api_name, window_start);

-- Create GIN indexes for JSONB
CREATE INDEX idx_system_logs_details ON system_logs USING GIN(details);

-- Automatic cleanup function for old data (keep only 1 year)
CREATE OR REPLACE FUNCTION cleanup_old_data()
RETURNS void AS $$
BEGIN
    -- Clean up old price data (older than 1 year)
    DELETE FROM stock_prices WHERE date < CURRENT_DATE - INTERVAL '1 year';

    -- Clean up old technical indicators (older than 1 year)
    DELETE FROM technical_indicators WHERE date < CURRENT_DATE - INTERVAL '1 year';

    -- Clean up old alerts (older than 3 months)
    DELETE FROM alerts WHERE created_at < NOW() - INTERVAL '3 months';

    -- Clean up old system logs (older than 3 months)
    DELETE FROM system_logs WHERE created_at < NOW() - INTERVAL '3 months';

    -- Clean up old rate limit records (older than 1 day)
    DELETE FROM api_rate_limits WHERE created_at < NOW() - INTERVAL '1 day';

    RAISE NOTICE 'Old data cleanup completed';
END;
$$ LANGUAGE plpgsql;

-- Update timestamps trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply update triggers
CREATE TRIGGER update_stocks_updated_at
    BEFORE UPDATE ON stocks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_portfolios_updated_at
    BEFORE UPDATE ON portfolios
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_portfolio_holdings_updated_at
    BEFORE UPDATE ON portfolio_holdings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_telegram_users_updated_at
    BEFORE UPDATE ON telegram_users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert some basic market data
INSERT INTO stocks (symbol, name, market, industry) VALUES
('2330', '台積電', 'TSE', '半導體'),
('2454', '聯發科', 'TSE', '半導體'),
('2317', '鴻海', 'TSE', '電子'),
('2412', '中華電', 'TSE', '通信'),
('2308', '台達電', 'TSE', '電子'),
('1301', '台塑', 'TSE', '塑膠'),
('1303', '南亞', 'TSE', '塑膠'),
('2002', '中鋼', 'TSE', '鋼鐵'),
('2886', '兆豐金', 'TSE', '金融'),
('2891', '中信金', 'TSE', '金融');

COMMENT ON DATABASE tw_stock IS 'Taiwan Stock Monitoring Robot Database';
COMMENT ON TABLE stocks IS '股票主檔';
COMMENT ON TABLE stock_prices IS '股價歷史資料';
COMMENT ON TABLE stock_realtime IS '即時股價資料';
COMMENT ON TABLE technical_indicators IS '技術指標';
COMMENT ON TABLE alerts IS '警報訊號';
COMMENT ON TABLE portfolios IS '投資組合';
COMMENT ON TABLE portfolio_holdings IS '投資組合持股';
COMMENT ON TABLE transactions IS '交易記錄';
COMMENT ON TABLE telegram_users IS 'Telegram用戶設定';
COMMENT ON TABLE watchlists IS '關注清單';
COMMENT ON TABLE system_logs IS '系統日誌';
COMMENT ON TABLE api_rate_limits IS 'API速率限制';

-- Grant permissions (adjust as needed)
-- CREATE USER tw_stock_user WITH PASSWORD 'your_secure_password';
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tw_stock_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO tw_stock_user;