const express = require('express');
const path = require('path');
const { checkVAT } = require('./vatChecker');
const app = express();
const port = process.env.PORT || 6000;

app.use(express.json());

// Serve the index.html file from the root directory
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

app.post('/check-vat', async (req, res) => {
    const { countryCode, vatNumber } = req.body;
    const result = await checkVAT(countryCode, vatNumber);
    res.json(result);
});

app.listen(port, () => {
    console.log(`VAT ID checker server running at http://localhost:${port}`);
});
