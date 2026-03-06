-- ReelHouse Database Initialization
USE `reelhouse_db`;

CREATE TABLE members (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  display_name VARCHAR(200),
  tier_id INT DEFAULT 1,
  role VARCHAR(50) DEFAULT 'member',
  email VARCHAR(200),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE movies (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(300) NOT NULL,
  genre VARCHAR(100),
  duration_min INT,
  rating VARCHAR(10),
  synopsis TEXT,
  poster_color VARCHAR(7) DEFAULT '#333'
) ENGINE=InnoDB;

CREATE TABLE screenings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  movie_id INT NOT NULL,
  screen_room VARCHAR(50),
  show_date DATE,
  show_time TIME,
  price DECIMAL(6,2),
  FOREIGN KEY (movie_id) REFERENCES movies(id)
) ENGINE=InnoDB;

CREATE TABLE reviews (
  id INT AUTO_INCREMENT PRIMARY KEY,
  member_id INT NOT NULL,
  movie_id INT NOT NULL,
  rating INT,
  review_text TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (member_id) REFERENCES members(id),
  FOREIGN KEY (movie_id) REFERENCES movies(id)
) ENGINE=InnoDB;

CREATE TABLE distributions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(300) NOT NULL,
  distributor VARCHAR(200),
  format_type VARCHAR(50),
  status VARCHAR(50) DEFAULT 'pending',
  print_ref VARCHAR(100),
  notes TEXT,
  approved_at DATETIME,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE supplier_orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  supplier_name VARCHAR(200),
  item_name VARCHAR(200),
  quantity INT,
  status VARCHAR(50) DEFAULT 'pending',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE supplier_notes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  content TEXT,
  tag VARCHAR(200) DEFAULT 'general',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE inventory (
  id INT AUTO_INCREMENT PRIMARY KEY,
  item_name VARCHAR(200),
  category VARCHAR(100),
  quantity INT DEFAULT 0,
  unit VARCHAR(50),
  reorder_level INT DEFAULT 10
) ENGINE=InnoDB;

CREATE TABLE system_config (
  id INT AUTO_INCREMENT PRIMARY KEY,
  config_key VARCHAR(200) NOT NULL UNIQUE,
  config_value VARCHAR(500)
) ENGINE=InnoDB;

CREATE TABLE equipment (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(200),
  equipment_group VARCHAR(10),
  room_number VARCHAR(10),
  status VARCHAR(50) DEFAULT 'operational',
  last_check DATETIME
) ENGINE=InnoDB;

CREATE TABLE calibration_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  equipment_id INT,
  log_entry TEXT,
  logged_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (equipment_id) REFERENCES equipment(id)
) ENGINE=InnoDB;

CREATE TABLE equipment_pins (
  id INT AUTO_INCREMENT PRIMARY KEY,
  pin VARCHAR(10) NOT NULL,
  equipment_group VARCHAR(10),
  active TINYINT DEFAULT 1
) ENGINE=InnoDB;

-- Seed: Members
INSERT INTO members (username, password_hash, display_name, tier_id, role, email) VALUES
('moviefan', 'screens2024', 'Jordan Rivers', 1, 'member', 'jordan@example.com'),
('cinephile99', 'popcorn2024', 'Alex Marsh', 2, 'member', 'alex@example.com'),
('nightowl', 'midnight1', 'Sam Keane', 1, 'member', 'sam@example.com');

-- Seed: Movies
INSERT INTO movies (title, genre, duration_min, rating, synopsis, poster_color) VALUES
('Midnight Aurora', 'Sci-Fi', 142, 'PG-13', 'A lone astronomer discovers a signal from beyond the solar system that changes everything.', '#1a237e'),
('The Quiet Acre', 'Drama', 118, 'PG', 'A retired farmer reconnects with old friends when a mysterious letter arrives.', '#2e7d32'),
('Neon District', 'Thriller', 126, 'R', 'An undercover reporter infiltrates a shadowy network operating out of an abandoned arcade.', '#c62828'),
('Paper Compass', 'Adventure', 104, 'PG', 'Two siblings follow hand-drawn maps through the Scottish Highlands.', '#ef6c00'),
('Glass Meridian', 'Mystery', 131, 'PG-13', 'A glass artist inherits a gallery with a hidden room that holds decades of secrets.', '#4a148c'),
('Wren Song', 'Animation', 96, 'G', 'A tiny bird with a big voice embarks on a cross-continent migration.', '#00695c');

-- Seed: Screenings
INSERT INTO screenings (movie_id, screen_room, show_date, show_time, price) VALUES
(1, 'Screen A', '2025-03-15', '19:30:00', 14.50),
(1, 'Screen A', '2025-03-15', '22:00:00', 14.50),
(2, 'Screen B', '2025-03-15', '14:00:00', 12.00),
(2, 'Screen B', '2025-03-15', '17:00:00', 12.00),
(3, 'Screen C', '2025-03-15', '20:00:00', 15.00),
(3, 'Screen C', '2025-03-16', '21:30:00', 15.00),
(4, 'Screen A', '2025-03-16', '11:00:00', 10.00),
(4, 'Screen B', '2025-03-16', '13:30:00', 10.00),
(5, 'Screen C', '2025-03-16', '18:00:00', 14.50),
(6, 'Screen A', '2025-03-16', '10:00:00', 9.00),
(6, 'Screen B', '2025-03-17', '11:00:00', 9.00),
(1, 'Screen C', '2025-03-17', '20:00:00', 14.50);

-- Seed: Reviews
INSERT INTO reviews (member_id, movie_id, rating, review_text) VALUES
(1, 1, 5, 'Absolutely mesmerizing. The cinematography during the aurora sequences is breathtaking.'),
(2, 2, 4, 'A gentle, heartfelt story. Perfect Sunday matinee material.'),
(1, 3, 4, 'Intense and stylish. The arcade scenes are unforgettable.'),
(3, 6, 5, 'My kids loved it and honestly so did I. Beautiful animation.');

-- Seed: Distributions
INSERT INTO distributions (title, distributor, format_type, status, print_ref, notes) VALUES
('Midnight Aurora', 'Stellar Distribution Co.', 'DCP', 'received', 'PRT-0837-NVLD', 'Print received and verified. Screen A projection ready.'),
('The Quiet Acre', 'Heritage Films Ltd.', 'DCP', 'shipped', 'PRT-1204-QKFM', 'In transit from regional hub. Expected by Thursday.'),
('Neon District', 'Pinnacle Releasing', '35mm', 'received', 'PRT-0562-RTYN', 'Special 35mm print for weekend retrospective.'),
('Paper Compass', 'Wanderlust Pictures', 'DCP', 'received', 'PRT-0991-HBJW', 'Family screening package with bonus shorts.'),
('Glass Meridian', 'Enigma Distribution', 'DCP', 'pending', 'PRT-1387-LDSE', 'Awaiting distributor confirmation for next week.'),
('Wren Song', 'Fable Animation Studio', 'DCP', 'received', 'PRT-0445-WMCX', 'Animation festival circuit print. Handle with care.'),
('Restricted: Internal Review Copy', 'ReelHouse Archive', 'Digital', 'pending', 'PRT-9999-RSTR', 'RESTRICTED. Administrative approval required for clearance certificate generation.');

-- Seed: Supplier Orders
INSERT INTO supplier_orders (supplier_name, item_name, quantity, status) VALUES
('Golden Kernel Supplies', 'Premium Popcorn Kernels 25kg', 12, 'delivered'),
('Fizz & Co Beverages', 'Sparkling Water Crates', 24, 'confirmed'),
('Sweet Tooth Confections', 'Assorted Candy Boxes', 48, 'pending'),
('Golden Kernel Supplies', 'Coconut Oil 10L', 6, 'delivered'),
('CupCraft Paper Goods', 'Large Popcorn Tubs 500ct', 3, 'confirmed'),
('Fizz & Co Beverages', 'Cola Syrup 20L', 8, 'pending');

-- Seed: Supplier Notes
INSERT INTO supplier_notes (content, tag) VALUES
('Golden Kernel delivery confirmed for Monday. Dock B.', 'delivery'),
('Sweet Tooth invoice #4821 needs approval before next order.', 'billing'),
('CupCraft minimum order quantity increased to 500 units.', 'policy'),
('Fizz & Co offering 10 percent discount on bulk syrup orders this quarter.', 'promo');

-- Seed: Inventory
INSERT INTO inventory (item_name, category, quantity, unit, reorder_level) VALUES
('Popcorn Kernels', 'Snacks', 180, 'kg', 50),
('Cola Syrup', 'Beverages', 45, 'L', 20),
('Sparkling Water', 'Beverages', 72, 'crates', 15),
('Candy Assortment', 'Snacks', 210, 'boxes', 30),
('Popcorn Tubs (L)', 'Supplies', 1200, 'units', 200);

-- Seed: System Config
INSERT INTO system_config (config_key, config_value) VALUES
('prints_admin_key', 'rh-prints-key-8f3a7d2e'),
('supplier_auth_token', 'PRT-0837-NVLD'),
('system_version', '2.4.1'),
('maintenance_mode', 'false');

-- Seed: Equipment
INSERT INTO equipment (name, equipment_group, room_number, status, last_check) VALUES
('Barco SP4K-15C Projector', 'A', '01', 'operational', '2025-03-14 09:00:00'),
('Barco SP4K-15C Projector', 'A', '02', 'operational', '2025-03-14 09:30:00'),
('Christie CP4330-RGB Projector', 'A', '03', 'maintenance', '2025-03-13 14:00:00'),
('Dolby IMS3000 Media Server', 'A', '04', 'operational', '2025-03-14 10:00:00');

-- Seed: Calibration Logs
INSERT INTO calibration_logs (equipment_id, log_entry, logged_at) VALUES
(1, 'Routine color calibration completed. DCI-P3 gamut verified within tolerance.', '2025-03-14 09:15:00'),
(1, 'Lens alignment check passed. Focus ring at 2.4m throw distance.', '2025-03-14 09:20:00'),
(2, 'Audio sync test passed. Latency measured at 4ms (within spec).', '2025-03-14 09:35:00'),
(2, 'Lamp hours: 1247/2000. Replacement scheduled for next month.', '2025-03-14 09:40:00'),
(3, 'FAULT: Color wheel intermittent failure detected during test pattern. Maintenance ticket filed.', '2025-03-13 14:10:00'),
(3, 'Projector taken offline pending parts delivery from Christie service.', '2025-03-13 14:30:00'),
(4, 'Print delivery for Midnight Aurora received. Ref: PRT-0837-NVLD. Filed under pantry supplier intake.', '2025-03-14 10:05:00'),
(4, 'Media server firmware updated to v3.2.1. All DCP playback tests nominal.', '2025-03-14 10:20:00');

-- Seed: Equipment PINs
INSERT INTO equipment_pins (pin, equipment_group, active) VALUES
('0436', 'A', 1);