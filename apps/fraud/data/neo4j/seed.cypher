UNWIND [
  {id: 'C1001', name: 'Alice Smith', risk: 'high'},
  {id: 'C1002', name: 'Bob Jones', risk: 'normal'},
  {id: 'C1003', name: 'Carol Patel', risk: 'medium'},
  {id: 'C1004', name: 'David Chen', risk: 'normal'},
  {id: 'C1005', name: 'Evan Brooks', risk: 'high'},
  {id: 'C1006', name: 'Farah Khan', risk: 'medium'},
  {id: 'C1007', name: 'Grace Miller', risk: 'normal'},
  {id: 'C1008', name: 'Hugo Silva', risk: 'normal'},
  {id: 'C1009', name: 'Imani Reed', risk: 'medium'},
  {id: 'C1010', name: 'Jonas Weber', risk: 'normal'}
] AS row
MERGE (n:Customer {id: row.id}) SET n += row;

UNWIND [
  {id: 'A1001', customer_id: 'C1001', status: 'active'},
  {id: 'A1002', customer_id: 'C1001', status: 'active'},
  {id: 'A1003', customer_id: 'C1002', status: 'active'},
  {id: 'A1004', customer_id: 'C1003', status: 'frozen'},
  {id: 'A1005', customer_id: 'C1004', status: 'active'},
  {id: 'A1006', customer_id: 'C1005', status: 'active'},
  {id: 'A1007', customer_id: 'C1005', status: 'active'},
  {id: 'A1008', customer_id: 'C1006', status: 'active'},
  {id: 'A1009', customer_id: 'C1007', status: 'closed'},
  {id: 'A1010', customer_id: 'C1008', status: 'active'},
  {id: 'A1011', customer_id: 'C1009', status: 'active'},
  {id: 'A1012', customer_id: 'C1010', status: 'active'},
  {id: 'A1013', customer_id: 'C1002', status: 'active'},
  {id: 'A1014', customer_id: 'C1003', status: 'active'},
  {id: 'A1015', customer_id: 'C1004', status: 'active'},
  {id: 'A1016', customer_id: 'C1006', status: 'active'}
] AS row
MERGE (n:Account {id: row.id}) SET n += row;

UNWIND [
  {id: 'D5001', device_type: 'mobile', risk: 'high'},
  {id: 'D5002', device_type: 'web', risk: 'normal'},
  {id: 'D5003', device_type: 'mobile', risk: 'normal'},
  {id: 'D5004', device_type: 'mobile', risk: 'high'},
  {id: 'D5005', device_type: 'web', risk: 'normal'},
  {id: 'D5006', device_type: 'mobile', risk: 'normal'},
  {id: 'D5007', device_type: 'tablet', risk: 'normal'},
  {id: 'D5008', device_type: 'web', risk: 'medium'}
] AS row
MERGE (n:Device {id: row.id}) SET n += row;

UNWIND [
  {id: 'M7001', name: 'Northwind Electronics', risk: 'high'},
  {id: 'M7002', name: 'Green Market', risk: 'normal'},
  {id: 'M7003', name: 'Rapid Digital Goods', risk: 'medium'},
  {id: 'M7004', name: 'Silverline Travel', risk: 'normal'},
  {id: 'M7005', name: 'Vertex Mobile', risk: 'high'},
  {id: 'M7006', name: 'Harbor Pharmacy', risk: 'normal'}
] AS row
MERGE (n:Merchant {id: row.id}) SET n += row;

UNWIND [
  {id: 'ADDR8001', city: 'London', country: 'GB'},
  {id: 'ADDR8002', city: 'Manchester', country: 'GB'},
  {id: 'ADDR8003', city: 'Birmingham', country: 'GB'},
  {id: 'ADDR8004', city: 'Leeds', country: 'GB'},
  {id: 'ADDR8005', city: 'Bristol', country: 'GB'},
  {id: 'ADDR8006', city: 'Glasgow', country: 'GB'},
  {id: 'ADDR8007', city: 'Cardiff', country: 'GB'},
  {id: 'ADDR8008', city: 'Liverpool', country: 'GB'}
] AS row
MERGE (n:Address {id: row.id}) SET n += row;

UNWIND [
  {id: 'F9001', status: 'open', severity: 'high'},
  {id: 'F9002', status: 'monitoring', severity: 'medium'},
  {id: 'F9003', status: 'open', severity: 'high'},
  {id: 'F9004', status: 'closed', severity: 'medium'},
  {id: 'F9005', status: 'monitoring', severity: 'low'},
  {id: 'F9006', status: 'open', severity: 'medium'}
] AS row
MERGE (n:FraudCase {id: row.id}) SET n += row;

UNWIND [
  {id: 'ALERT6001', alert_type: 'shared_device', status: 'open'},
  {id: 'ALERT6002', alert_type: 'velocity', status: 'open'},
  {id: 'ALERT6003', alert_type: 'watchlist_merchant', status: 'closed'},
  {id: 'ALERT6004', alert_type: 'transaction_velocity', status: 'open'},
  {id: 'ALERT6005', alert_type: 'high_value_activity', status: 'open'},
  {id: 'ALERT6006', alert_type: 'reversal_pattern', status: 'closed'},
  {id: 'ALERT6007', alert_type: 'merchant_review', status: 'closed'},
  {id: 'ALERT6008', alert_type: 'watchlist_merchant', status: 'open'},
  {id: 'ALERT6009', alert_type: 'unusual_location', status: 'closed'},
  {id: 'ALERT6010', alert_type: 'shared_device_review', status: 'closed'},
  {id: 'ALERT6011', alert_type: 'merchant_review', status: 'closed'},
  {id: 'ALERT6012', alert_type: 'account_review', status: 'closed'}
] AS row
MERGE (n:FraudAlert {id: row.id}) SET n += row;

MATCH (c1:Customer {id: 'C1001'}), (a1:Account {id: 'A1001'}), (a2:Account {id: 'A1002'}),
      (d1:Device {id: 'D5001'}), (d2:Device {id: 'D5002'}), (addr:Address {id: 'ADDR8001'}),
      (f1:FraudCase {id: 'F9001'}), (alert1:FraudAlert {id: 'ALERT6001'}),
      (alert2:FraudAlert {id: 'ALERT6002'})
MERGE (c1)-[:OWNS]->(a1)
MERGE (c1)-[:OWNS]->(a2)
MERGE (c1)-[:USES]->(d1)
MERGE (c1)-[:USES]->(d2)
MERGE (c1)-[:LIVES_AT]->(addr)
MERGE (c1)-[:INVOLVED_IN]->(f1)
MERGE (a1)-[:HAS_ALERT]->(alert1)
MERGE (a1)-[:HAS_ALERT]->(alert2);

MATCH (c2:Customer {id: 'C1002'}), (a3:Account {id: 'A1003'}), (d1:Device {id: 'D5001'}),
      (a13:Account {id: 'A1013'}),
      (addr:Address {id: 'ADDR8002'})
MERGE (c2)-[:OWNS]->(a3)
MERGE (c2)-[:OWNS]->(a13)
MERGE (c2)-[:USES]->(d1)
MERGE (c2)-[:LIVES_AT]->(addr);

MATCH (c3:Customer {id: 'C1003'}), (a4:Account {id: 'A1004'}), (a14:Account {id: 'A1014'}),
      (d3:Device {id: 'D5003'}), (addr:Address {id: 'ADDR8002'}),
      (f2:FraudCase {id: 'F9002'}), (alert3:FraudAlert {id: 'ALERT6003'})
MERGE (c3)-[:OWNS]->(a4)
MERGE (c3)-[:OWNS]->(a14)
MERGE (c3)-[:USES]->(d3)
MERGE (c3)-[:LIVES_AT]->(addr)
MERGE (c3)-[:INVOLVED_IN]->(f2)
MERGE (a4)-[:HAS_ALERT]->(alert3);

MATCH (c4:Customer {id: 'C1004'}), (a5:Account {id: 'A1005'}), (a15:Account {id: 'A1015'}),
      (addr:Address {id: 'ADDR8003'})
MERGE (c4)-[:OWNS]->(a5)
MERGE (c4)-[:OWNS]->(a15);

MATCH (c5:Customer {id: 'C1005'}), (a6:Account {id: 'A1006'}), (a7:Account {id: 'A1007'}),
      (d4:Device {id: 'D5004'}), (addr:Address {id: 'ADDR8004'}),
      (f3:FraudCase {id: 'F9003'}), (alert4:FraudAlert {id: 'ALERT6004'}),
      (alert5:FraudAlert {id: 'ALERT6005'})
MERGE (c5)-[:OWNS]->(a6)
MERGE (c5)-[:OWNS]->(a7)
MERGE (c5)-[:USES]->(d4)
MERGE (c5)-[:LIVES_AT]->(addr)
MERGE (c5)-[:INVOLVED_IN]->(f3)
MERGE (a6)-[:HAS_ALERT]->(alert4)
MERGE (a6)-[:HAS_ALERT]->(alert5);

MATCH (c6:Customer {id: 'C1006'}), (a8:Account {id: 'A1008'}), (a16:Account {id: 'A1016'}),
      (d5:Device {id: 'D5005'}),
      (addr:Address {id: 'ADDR8005'}), (f4:FraudCase {id: 'F9004'}),
      (alert6:FraudAlert {id: 'ALERT6006'})
MERGE (c6)-[:OWNS]->(a8)
MERGE (c6)-[:OWNS]->(a16)
MERGE (c6)-[:USES]->(d5)
MERGE (c6)-[:INVOLVED_IN]->(f4);

MATCH (c7:Customer {id: 'C1007'}), (a9:Account {id: 'A1009'}),
      (d6:Device {id: 'D5006'}),
      (addr:Address {id: 'ADDR8006'})
MERGE (c7)-[:OWNS]->(a9)
MERGE (c7)-[:USES]->(d6);

MATCH (c8:Customer {id: 'C1008'}), (a10:Account {id: 'A1010'}), (d7:Device {id: 'D5007'}),
      (addr:Address {id: 'ADDR8007'}), (f5:FraudCase {id: 'F9005'}),
      (alert7:FraudAlert {id: 'ALERT6007'}), (m1:Merchant {id: 'M7001'})
MERGE (c8)-[:OWNS]->(a10)
MERGE (c8)-[:USES]->(d7);

MATCH (c9:Customer {id: 'C1009'}), (a11:Account {id: 'A1011'}), (d8:Device {id: 'D5008'}),
      (addr:Address {id: 'ADDR8008'}), (f6:FraudCase {id: 'F9006'}),
      (alert8:FraudAlert {id: 'ALERT6008'}), (m3:Merchant {id: 'M7003'})
MERGE (c9)-[:OWNS]->(a11)
MERGE (c9)-[:USES]->(d8);

MATCH (c10:Customer {id: 'C1010'}), (a12:Account {id: 'A1012'}), (d3:Device {id: 'D5003'}),
      (addr:Address {id: 'ADDR8002'}), (alert9:FraudAlert {id: 'ALERT6009'}),
      (m4:Merchant {id: 'M7004'})
MERGE (c10)-[:OWNS]->(a12);

MATCH (c1:Customer {id: 'C1001'}), (c2:Customer {id: 'C1002'}),
      (c3:Customer {id: 'C1003'})
MERGE (c1)-[:SHARES_DEVICE_WITH]->(c2)
MERGE (c2)-[:SHARES_ADDRESS_WITH]->(c3);
