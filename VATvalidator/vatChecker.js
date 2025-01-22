const soap = require('soap');

const url = 'https://ec.europa.eu/taxation_customs/vies/checkVatService.wsdl';

async function checkVAT(vatCountryCode, vatNumber) {
    try {
        const client = await soap.createClientAsync(url);
        const [result] = await client.checkVatAsync({ countryCode: vatCountryCode, vatNumber: vatNumber });
        return result;
    } catch (error) {
        return { error: error.message };
    }
}

module.exports = { checkVAT };
