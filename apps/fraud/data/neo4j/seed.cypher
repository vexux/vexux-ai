UNWIND [
  {id: 'C1001', name: 'Alice Smith', risk: 'high'},
  {id: 'C1002', name: 'Bob Jones', risk: 'normal'},
  {id: 'C1003', name: 'Carol Patel', risk: 'medium'},
  {id: 'C1004', name: 'David Chen', risk: 'normal'}
] AS row
MERGE (n:Customer {id: row.id}) SET n += row;

UNWIND [
  {id: 'A1001', customer_id: 'C1001', status: 'active'},
  {id: 'A1002', customer_id: 'C1001', status: 'active'},
  {id: 'A1003', customer_id: 'C1002', status: 'active'},
  {id: 'A1004', customer_id: 'C1003', status: 'frozen'},
  {id: 'A1005', customer_id: 'C1004', status: 'active'}
] AS row
MERGE (n:Account {id: row.id}) SET n += row;

UNWIND [
  {id: 'D5001', device_type: 'mobile', risk: 'high'},
  {id: 'D5002', device_type: 'web', risk: 'normal'},
  {id: 'D5003', device_type: 'mobile', risk: 'normal'}
] AS row
MERGE (n:Device {id: row.id}) SET n += row;

UNWIND [
  {id: 'M7001', name: 'Northwind Electronics', risk: 'high'},
  {id: 'M7002', name: 'Green Market', risk: 'normal'},
  {id: 'M7003', name: 'Rapid Digital Goods', risk: 'medium'}
] AS row
MERGE (n:Merchant {id: row.id}) SET n += row;

UNWIND [
  {id: 'ADDR8001', city: 'London', country: 'GB'},
  {id: 'ADDR8002', city: 'Manchester', country: 'GB'},
  {id: 'ADDR8003', city: 'Birmingham', country: 'GB'}
] AS row
MERGE (n:Address {id: row.id}) SET n += row;

UNWIND [
  {id: 'F9001', status: 'open', severity: 'high'},
  {id: 'F9002', status: 'monitoring', severity: 'medium'}
] AS row
MERGE (n:FraudCase {id: row.id}) SET n += row;

UNWIND [
  {id: 'ALERT6001', alert_type: 'shared_device', status: 'open'},
  {id: 'ALERT6002', alert_type: 'velocity', status: 'open'},
  {id: 'ALERT6003', alert_type: 'watchlist_merchant', status: 'closed'}
] AS row
MERGE (n:FraudAlert {id: row.id}) SET n += row;

MATCH (c1:Customer {id: 'C1001'}), (a1:Account {id: 'A1001'}), (a2:Account {id: 'A1002'}),
      (d1:Device {id: 'D5001'}), (d2:Device {id: 'D5002'}), (addr:Address {id: 'ADDR8001'}),
      (f1:FraudCase {id: 'F9001'}), (alert1:FraudAlert {id: 'ALERT6001'})
MERGE (c1)-[:OWNS]->(a1)
MERGE (c1)-[:OWNS]->(a2)
MERGE (c1)-[:USES]->(d1)
MERGE (c1)-[:USES]->(d2)
MERGE (c1)-[:LIVES_AT]->(addr)
MERGE (c1)-[:INVOLVED_IN]->(f1)
MERGE (a1)-[:HAS_ALERT]->(alert1);

MATCH (c2:Customer {id: 'C1002'}), (a3:Account {id: 'A1003'}), (d1:Device {id: 'D5001'}),
      (addr:Address {id: 'ADDR8002'}), (m1:Merchant {id: 'M7002'})
MERGE (c2)-[:OWNS]->(a3)
MERGE (c2)-[:USES]->(d1)
MERGE (c2)-[:LIVES_AT]->(addr)
MERGE (a3)-[:USED_AT]->(m1);

MATCH (c3:Customer {id: 'C1003'}), (a4:Account {id: 'A1004'}), (d3:Device {id: 'D5003'}),
      (addr:Address {id: 'ADDR8002'}), (f2:FraudCase {id: 'F9002'}), (alert2:FraudAlert {id: 'ALERT6002'})
MERGE (c3)-[:OWNS]->(a4)
MERGE (c3)-[:USES]->(d3)
MERGE (c3)-[:LIVES_AT]->(addr)
MERGE (c3)-[:INVOLVED_IN]->(f2)
MERGE (a4)-[:HAS_ALERT]->(alert2);

MATCH (c4:Customer {id: 'C1004'}), (a5:Account {id: 'A1005'}), (d2:Device {id: 'D5002'}),
      (addr:Address {id: 'ADDR8003'}), (m3:Merchant {id: 'M7003'})
MERGE (c4)-[:OWNS]->(a5)
MERGE (c4)-[:USES]->(d2)
MERGE (c4)-[:LIVES_AT]->(addr)
MERGE (a5)-[:USED_AT]->(m3);

MATCH (c1:Customer {id: 'C1001'}), (c2:Customer {id: 'C1002'}), (c3:Customer {id: 'C1003'}),
      (addr:Address {id: 'ADDR8002'}), (d1:Device {id: 'D5001'})
MERGE (c1)-[:SHARES_DEVICE_WITH]->(c2)
MERGE (c2)-[:SHARES_DEVICE_WITH]->(c1)
MERGE (c2)-[:SHARES_ADDRESS_WITH]->(c3)
MERGE (c3)-[:SHARES_ADDRESS_WITH]->(c2);
