// npm run db:load  → (re)creates data/invoice-guard.db from data/fixtures
import { openDb, loadFixtures } from "./index.js";

const db = openDb();
console.log("loaded", loadFixtures(db));
db.close();
