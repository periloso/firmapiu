#!/usr/bin/python

# sudo apt-get install python-pyasn1 python-pyasn1-modules python-pyscard python-rfc3161 python-pip python-m2crypto
# sudo pip install rfc3161

import os
import sys
import commands  # per usare al momento comandi bash
import libxml2
import hashlib
from argparse import ArgumentParser

import smartcard
from smartcard.util import toHexString
import PyKCS11
import hashlib
import rfc3161

from pyasn1.codec.der import encoder, decoder
from pyasn1_modules import rfc2459
from pyasn1.type import univ
import pycurl
import StringIO
#import config


def parse_argument():
    parser = ArgumentParser()
    parser.add_argument('--sign', help='Sign given filename')
    parser.add_argument('--verify', help='Verify given filename')
    result = parser.parse_args()


def get_smartcard_atr():
    """return the atr of the current device"""

    try:
        # ottengo la lista dei lettori
        readers_list = smartcard.System.readers()
    except smartcard.pcsc.PCSCExceptions.EstablishContextException:
        # il lettore di smartcard potrebbe non essere inserito
        return None, "demone pcscd not attivo\n"

    # non sono riuscito a trovare nessun lettore
    if len(readers_list) == 0:
        return None, "nessun lettore riconosciuto\n"

    # di default prendo il primo lettore
    reader = readers_list[0]

    connection = reader.createConnection()
    try:
        # Mi connetto e ottengo l'ATR dalla carta
        connection.connect()
        atr_str = toHexString(connection.getATR()).replace(" ", ":").lower()
        connection.disconnect()
    except smartcard.Exceptions.CardConnectionException, e:
        return None, "smartcard non inserita\n"

    return atr_str, ""


def get_smartcard_library(atr_str):
    """in base all'atr restituisco quale libreria e' utile usare"""

    # carico il file xml con le librerie e cerco la libreria relativa all'ATR
    doc = libxml2.parseFile("libraries.xml")
    # in base all'atr cerco nel file usando XPATH
    library_result = doc.xpathEval("//key[text()='%s']/../@path" % atr_str)
    # se non trovo nessun risultato
    if len(library_result) == 0:
        return None, "non ho trovato nessuna libreria\n"

    # ottengo il path della libreria
    library_used = library_result[0].get_content()
    return library_used, ""


def get_serial(library_path):
    pkcs11 = PyKCS11.PyKCS11Lib()
    pkcs11.load(library_path)
    return pkcs11.getTokenInfo(0).serialNumber


def decode_trs():
    id_attribute_messageDigest = univ.ObjectIdentifier((1, 2, 840, 113549, 1, 9, 4,))

    #fileTSR = open("rfc3161.java.tsr", "rb")
    fileTSR = open("provaTSR.tsr", "rb")
    tst_response, substrate = decoder.decode(fileTSR.read(),
                                             asn1Spec=rfc3161.TimeStampResp())

    tst = tst_response.time_stamp_token  # Time Stamp Token
    #hashObj = hashlib.new("sha256")
    #hashObj.update("pippo")
    #digest = hashObj.digest()
    signed_data = tst.content

    message_imprint = tst.tst_info.message_imprint

    print rfc3161.__dict__["id_sha256"]

    # controllo la hash del file sha256
    print message_imprint.hash_algorithm[0]
    if message_imprint.hashed_message != "HASH_SUM":
        print 'Message imprint mismatch'

    # Controllo che ci sia almeno una firma
    if not len(signed_data['signerInfos']):
        print 'No signature'

    # Prendo la prima firma
    signer_info = signed_data['signerInfos'][0]
    # Ottengo i contenuti
    content_info = signed_data['contentInfo']

    if content_info['contentType'] != rfc3161.id_ct_TSTInfo:
        print 'Wrong Content Type'

    content = str(decoder.decode(str(content_info['content']),
                                 asn1Spec=univ.OctetString())[0])

    # Controllo se ci sono degli attributi firmati
    if not len(signer_info['authenticatedAttributes']):
        signed_data = content
    else:
        # if there is authenticated attributes, they must contain the message
        # digest and they are the signed data otherwise the content is the
        # signed data
        authenticated_attributes = signer_info['authenticatedAttributes']
        signer_digest_algorithm = signer_info['digestAlgorithm']['algorithm']

        for authenticated_attribute in authenticated_attributes:
            if authenticated_attribute[0] == id_attribute_messageDigest:
                signed_digest = str(decoder.decode(str(authenticated_attribute[1][0]),
                                                   asn1Spec=univ.OctetString())[0])
                if signed_digest != content_digest:
                    print 'content digest differs from signed digest'
                    s = univ.SetOf()
                    for i, x in enumerate(authenticated_attributes):
                        s.setComponentByPosition(i, x)
                    signed_data = encoder.encode(s)
                    break

    # controllo la firma
    signature = signer_info['encryptedDigest']
    pub_key = certificate.get_pubkey()  # ???? dove lo prendo il certificato
    pub_key.reset_context(signer_hash_name)
    pub_key.verify_init()
    pub_key.verify_update(signed_data)
    if pub_key.verify_final(str(signature)) != 1:
        print 'Bad signature'

    print 'OK signature'


def get_id_cert():
    CNS_ID_TUPLE = (67, 78, 83, 48)
    DS_ID_TUPLE = (68, 83, 49)

    library_path = sys.argv[1]
    pkcs11 = PyKCS11.PyKCS11Lib()
    pkcs11.load(library_path)
    session = pkcs11.openSession(0)
    objects = session.findObjects(template=())

    all_attributes = PyKCS11.CKA.keys()
    all_attributes.remove(PyKCS11.CKA_PRIVATE_EXPONENT)
    all_attributes.remove(PyKCS11.CKA_PRIME_1)
    all_attributes.remove(PyKCS11.CKA_PRIME_2)
    all_attributes.remove(PyKCS11.CKA_EXPONENT_1)
    all_attributes.remove(PyKCS11.CKA_EXPONENT_2)
    all_attributes.remove(PyKCS11.CKA_COEFFICIENT)
    all_attributes = [e for e in all_attributes if isinstance(e, int)]

    for obj in objects:
        attributes = session.getAttributeValue(obj, all_attributes)
        attrDict = dict(zip(all_attributes, attributes))
        #print "Classe", PyKCS11.CKO[attrDict[PyKCS11.CKA_CLASS]] # Lista le classi
        #keyType = attrDict[PyKCS11.CKA_KEY_TYPE]
        #if keyType != None:
        #	print "Tipo di chiave", PyKCS11.CKK[keyType] # Lista per i tipi di chiave
        #certType = attrDict[PyKCS11.CKA_CERTIFICATE_TYPE]
        #if certType != None:
        #	print "Tipo certificato", PyKCS11.CKC[certType] # Lista per i tipi di certificato
        #print "########################################################"

        # Filtro per i certificati
        if attrDict[PyKCS11.CKA_CLASS] == PyKCS11.CKO_CERTIFICATE and \
                        attrDict[PyKCS11.CKA_CERTIFICATE_TYPE] == PyKCS11.CKC_X_509:
            print attrDict[PyKCS11.CKA_LABEL]

            for hexValue in attrDict[PyKCS11.CKA_ID]:
                print hexx(hexValue).decode('hex')

            if attrDict[PyKCS11.CKA_ID] == DS_ID_TUPLE:
                print "OK"  # Ho trovato il certificato per firmare il file


def hexx(intval):
    x = hex(intval)[2:]
    if (x[-1:].upper() == 'L'):
        x = x[:-1]
    if len(x) % 2 != 0:
        return "0%s" % x
    return x


def create_timestamp_query(filename):
    if not os.path.exists(filename):
        return None, 'file non esistente'

    if not os.path.isfile(filename):
        return None, 'not a file'

    # calcolo l'hash 256 de file
    try:
        file_hash = open(filename, "rb")
        hash_obj = hashlib.sha256()
        hash_obj.update(file_hash.read())
        digest = hash_obj.digest()
    except:
        return None, 'failed to hash file'  # TODO da riverede la gestione delle eccezioni

    # costruisce l'oggetto richiesta
    algorithm_identifier = rfc2459.AlgorithmIdentifier()
    algorithm_identifier.setComponentByPosition(0, rfc3161.__dict__["id_sha256"])
    algorithm_identifier.setComponentByPosition(1, univ.Null())  # serve per Aruba
    message_imprint = rfc3161.MessageImprint()
    message_imprint.setComponentByPosition(0, algorithm_identifier)
    message_imprint.setComponentByPosition(1, digest)
    request = rfc3161.TimeStampReq()
    request.setComponentByPosition(0, 'v1')
    request.setComponentByPosition(1, message_imprint)
    request.setComponentByPosition(4, univ.Boolean(True))  # server per Aruba
    # codifico tutto in DER
    binary_request = encoder.encode(request)

    return binary_request, ""


def send_timestamp_query(server, username, password, binary_request):
    output, error_msg = web_request(
        site_url=server,
        http_username=username,
        http_password=password,
        data=binary_request,  # invio la query
        content_type="application/timestamp-query"
    )

    if output == None:
        return None, error_msg

    return output, ""


def aruba_timestamp_request(filename):
    binary_timestamp_request, error_msg = create_timestamp_query(filename)
    if binary_timestamp_request == None:
        return None, error_msg  # passo il messaggio al livello superiore

    if not config.read_config():
        return None, 'configurazioni non caricate'

    binary_timestamp_reply, error_msg = web_request(
        site_url=config.tsa_server,
        http_username=config.tsa_username,
        http_password=config.tsa_password,
        data=binary_timestamp_request,  # invio la query
        content_type="application/timestamp-query"
    )

    if binary_timestamp_reply == None:
        return None, error_msg

    return binary_timestamp_reply, ""


def web_request_header_callback(buff):
    sys.stdout.write(buff)


def web_request_debug_callback(debug_type, debug_msg):
    print "debug(%d): %s" % (debug_type, debug_msg)


def web_request(site_url, data=None, file_to_send=None, http_username=None,
                http_password=None, content_type=None):
    if site_url == None:
        return None, "non hai inserito l'url"

    if (http_username != None and http_password == None) or \
            (http_username == None and http_password != None):
        return None, "devi inserire username e password, non solo uno dei due"

    header_buff = StringIO.StringIO()
    buff = StringIO.StringIO()
    curl = pycurl.Curl()
    headers = []
    curl.setopt(pycurl.URL, site_url)
    #curl.setopt(pycurl.HEADERFUNCTION, web_request_header_callback)
    curl.setopt(pycurl.WRITEFUNCTION, buff.write)
    #curl.setopt(pycurl.VERBOSE, 1)
    curl.setopt(pycurl.DEBUGFUNCTION, web_request_debug_callback)

    if content_type != None:
        print 'set content_type', content_type
        headers.append("Content-Type: %s" % content_type)  # non e' necessario

    if http_username != None:  # se e' settato username ci sara' ancha la password
        print 'set authentication %s:%s' % (http_username, http_password)
        curl.setopt(pycurl.USERPWD, "%s:%s" % (http_username, http_password))

    if data != None:
        print 'set data', data
        curl.setopt(pycurl.POSTFIELDS, data)

    if file_to_send != None:
        print 'set file to send', file_to_send
        curl.setopt(pycurl.POST, 1)
        file_buff = open(file_to_send, "rb")
        file_buff_size = os.path.getsize(file_to_send)
        # aggiungo la grandezza del file
        headers.append("Content-Length: %d" % file_buff_size)  # e' necessario
        curl.setopt(pycurl.INFILESIZE, file_buff_size)
        curl.setopt(pycurl.READFUNCTION, file_buff.read)

    # appendo tutti gli hea
    curl.setopt(pycurl.HTTPHEADER, headers)

    try:
        curl.perform()
    except pycurl.error, error:
        return None, 'errore con pycurl'
    finally:
        curl.close()

    if file_to_send != None:
        file_buff.close()

    return buff.getvalue(), ""


def main():
    parse_argument()

if __name__ == '__main__':
    main()
