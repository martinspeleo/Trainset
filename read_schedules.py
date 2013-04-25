"""
Parses the National Rail CIF format
"""

# TODO:
#  - Investigate the semantics more thoroughly: particular Changes en
#    Route. If these bear fixed resemblance to the locations
#    before/after them, it may well make sense to parse the data
#    differently. Also, should associations associate things that are
#    already known?
#  - Write some sensible subclasses of ScheduleMachine, to place data
#    in databases, etc.



from datetime import date, datetime, time, timedelta
from warnings import warn

from base import *
from codes import Schedule, Misc



def y2k_coding(n):
    """
    The system used to enforce Year 2000 compliance. I guess they
    propose to worry about Year 2060 compliance when the time comes.
    """
    if n < 60:
        return 2000 + n
    else:
        return 1900 + n

def date_ddmmyy(s):
    return date(y2k_coding(int(s[4:6])), int(s[2:4]), int(s[0:2]))

def datetime_ddmmyyhhmm(s):
    """
    This is the single worst time encoding I have ever worked with.
    """
    return datetime(y2k_coding(int(s[4:6])), int(s[2:4]), int(s[0:2]), int(s[6:8]), int(s[8:10]))

def date_yymmdd(s):
    return date(y2k_coding(int(s[0:2])), int(s[2:4]), int(s[4:6]))

def time_hhmm(s):
    return time(int(s[0:2]), int(s[2:4]))

def time_hhmmx(s):
    if s.strip() == "":
        return None
    elif s[4] == "H":
        return time(int(s[0:2]), int(s[2:4]), 30)
    else:
        return time(int(s[0:2]), int(s[2:4]), 0)

def timedelta_minh(s):
    if s.strip() == "":
        return None
    elif s[1] == "H":
        return timedelta(minutes = int(s[0].strip() or 0), seconds = 30)
    else:
        return timedelta(minutes = int(s.strip()))


def parse_days(s):
    return dict(zip(Misc.days,(c == "1" for c in s)))


def parse_activities(s):
    activities = [s[i:i+2].strip() for i in xrange(0,len(s),2)]
    activities = [x for x in activities if x != ""]
    for x in activities:
        if x not in Schedule.train_activity:
            warn("activity = %r"%(x,), UnrecognisedWarning)
    return activities


def parse_timing_load(pt,s):
    "Takes a power type and a timing load"
    if pt == "DMU":
        if s in Schedule.dmu_timing_load:
            return Schedule.dmu_timing_load[s]
        elif s in set(["D1","D2","D3","D4","D1T"]):
            return s
    elif pt == "EMU":
        if s == "AT":
            return "Accelerated Timing"
        elif s.isdigit():
            return "EMU, type "+s
    elif pt in set(["D","E","ED"]):
        if s.isdigit():
            n = int(s)
            if n < 1000 or (n < 10000 and pt == "ED"):
                return s + " tonnes"
    return None


def linereader(expected_record_type):
    """
    Decorator for safely reading lines.
    """

    def method_maker(f):

        def method(self):
            if self.record_type == expected_record_type:
                f(self)
                self.nextline()
            else:
                warn("Record type mismatch: wanted %r; got %r"%(expected_record_type, self.record_type), WeirdBehaviour)

        return method

    return method_maker



class ScheduleMachine():
    """
    A class parsing schedules. Intended to be subclassed to specify
    the write methods (at the bottom), and begin() and end()
    """

    transaction_types = {"N": "new",
                         "D": "delete",
                         "R": "revise"}

    def nextline(self):
        try:
            self.line = next(self.iterator)
            self.record_type = self.line[:2]
        except StopIteration:
            self.line = None
            self.record_type = "EOF"

    
    @linereader("HD")
    def read_HD(self):
        # Header
        d = {}
        l = self.line

        d["user_identity"] = l[7:13]

        s = l[16:22].strip()
        if s:
            d["user_date"] = date_yymmdd(s)

        s = l[22:32].strip()
        if s:
            d["extracted_time"] = datetime_ddmmyyhhmm(s)

        d["reference"] = l[32:39].strip()

        previous_reference = l[39:46].strip()
        if previous_reference:
            d["previous_reference"] = previous_reference

        d["full"] = (l[46] == 'F')
        d["version"] = l[47]

        s = l[48:54].strip()
        if s:
            d["extract_start"] = date_ddmmyy(s)

        s = l[54:60].strip()
        if s:
            d["extract_end"] = date_ddmmyy(s)

        self.header = d


    @linereader("BS")
    def read_BS(self):
        # Basic schedule
        d = self.schedule
        l = self.line

        d["type"] = self.transaction_types[l[2]]
        d["uid"] = l[3:9]
        d["date_runs_from"] = date_yymmdd(l[9:15])
        if l[15:21] == "999999":
            d["date_runs_to"] = None
        else:
            d["date_runs_to"] = date_yymmdd(l[15:21])

        d["days_run"] = parse_days(l[21:28])

        bhx = l[28].strip()
        if bhx:
            d["bank_holiday_running"] = bhx
            if bhx not in Schedule.bhx:
                warn("bank holiday running code = %r"%(bhx,),UnrecognisedWarning)

        status = l[29].strip()
        if status:
            d["train_status"] = status
            if status not in Schedule.status:
                warn("status = %r"%(status,),UnrecognisedWarning)

        category = l[30:32].strip()
        if category:
            d["category"] = category
            if category not in Schedule.category:
                warn("category = %r"%(category,),UnrecognisedWarning)

        train_identity = l[32:36].strip()
        if train_identity:
            d["train_identity"] = train_identity

        d["headcode"] = l[36:40]
        d["train_service_code"] = l[41:49]
        d["portion_id"] = l[49]

        power_type = l[50:53].strip()
        if power_type:
            d["power_type"] = power_type
            if power_type not in Schedule.power_type:
                warn("power_type = %r"%(power_type,),UnrecognisedWarning)

        timing_load = l[53:57].strip()
        if timing_load:
            if parse_timing_load(power_type, timing_load) is None:
                warn("timing_load = %r (with power_type = %r)", (timing_load, power_type), UnrecognisedWarning)
            d["timing_load"] = timing_load

        d["speed"] = int(l[57:60].strip() or 0)

        operating_chars = list(l[60:66].strip())
        d["operating_chars"] = operating_chars
        for c in operating_chars:
            if c not in Schedule.operating_chars:
                warn("operating_chars has %r"%(c,),UnrecognisedWarning)

        train_class = l[66].strip() or "B"
        d["train_class"] = train_class
        if train_class not in Schedule.train_class:
            warn("train_class = %r"%(train_class,),UnrecognisedWarning)  
        sleepers = l[67].strip()
        if sleepers:
            d["sleepers"] = sleepers
            if sleepers not in Schedule.sleepers:
                warn("sleepers = %r"%(sleepers,),UnrecognisedWarning)

        reservations = l[68].strip()
        if reservations:
            d["reservations"] = reservations
            if reservations not in Schedule.reservations:
                warn("reservations = %r"%(sleepers,),UnrecognisedWarning)

        catering = list(l[69:73].strip())
        d["catering"] = catering
        for c in catering:
            if c not in Schedule.catering:
                warn("catering has %r"%(c,),UnrecognisedWarning)

        service_branding = list(l[73:77].strip())
        d["service_branding"] = service_branding
        for c in service_branding:
            if c not in Schedule.service_branding:
                warn("service_branding has %r"%(c,),UnrecognisedWarning)

        stp_indicator = l[79].strip()
        if stp_indicator not in Schedule.stp_indicator:
            warn("stp_indicator = %r"%(stp_indicator,),UnrecognisedWarning)
        d["stp_indicator"] = stp_indicator


    @linereader("BX")
    def read_BX(self):
        d = self.schedule
        l = self.line
        
        uic_code = l[6:11].strip()
        if uic_code:
            d["uic_code"] = uic_code

        atoc_code = l[11:13].strip()
        if atoc_code:
            d["atoc_code"] = atoc_code
            if atoc_code not in Schedule.atoc_code:
                warn("atoc_code = %r"%(atoc_code,), UnrecognisedWarning)

        atc = l[13].strip()
        if atc == "Y":
            d["applicable_timetable"] = True
        elif atc == "N":
            d["applicable_timetable"] = False
        elif atc != "":
            warn("atc = %r"%(atc,), UnrecognisedWarning)
            d["applicable_timetable"] = atc

        rsid = l[14:22].strip()
        if rsid:
            d["rsid"] = rsid

        data_source = l[22].strip()
        if data_source:
            d["data_source"] = data_source
            

    @linereader("TI")
    def read_TI(self):
        d = self.tiploc
        l = self.line

        d["type"] = "insert"
        d["tiploc_code"] = l[2:9]
        d["capitals"] = l[9:11].strip()
        d["nalco"] = l[11:17].strip()
        d["nlc_check"] = l[17]

        tps_description = l[18:44].strip()
        if tps_description:
            d["tps_description"] = tps_description

        d["po_mcp_code"] = l[49:53].strip()
        d["crs_code"] = l[53:56]

        description = l[56:72].strip()
        if description:
            d["description"] = description


    @linereader("TA")
    def read_TA(self):
        d = self.tiploc
        l = self.line
        d["type"] = "amend"
        d["tiploc_code"] = l[2:9]
        d["capitals"] = l[9:11].strip()
        d["nalco"] = l[11:17].strip()
        d["nlc_check"] = l[17]
        d["tps_description"] = l[18:44].strip()
        d["po_mcp_code"] = l[49:53].strip()
        d["crs_code"] = l[53:56]
        d["description"] = l[56:72].strip()
        d["new_tiploc_code"] = l[72:79]


    @linereader("TD")
    def read_TD(self):
        d = self.tiploc
        l = self.line
        d["type"] = "delete"
        d["tiploc_code"] = l[2:9]


    @linereader("AA")
    def read_AA(self):
        d = self.association
        l = self.line

        d["type"] = self.transaction_types[l[2]]
        d["main_uid"] = l[3:9].strip()
        d["associated_uid"] = l[9:15].strip()
        d["start_date"] = date_yymmdd(l[15:21])
        d["end_date"] = date_yymmdd(l[21:27])
        d["days"] = parse_days(l[27:34])

        category = l[34:36].strip()
        if category:
            d["category"] = Schedule.association_category[category]
        
        date_ind = l[36].strip()
        if date_ind:
            d["date_ind"] = date_ind
            if date_ind not in Schedule.association_date_ind:
                warn("date_ind = %r"%(date_ind,),UnrecognisedWarning)

        d["association_location"] = l[37:44].strip()

        base_suffix = l[44]
        if base_suffix not in [" ","2"]:
            warn("base_suffix = %r"%(base_suffix,),UnrecognisedWarning)
        d["base_suffix"] = base_suffix
        
        main_suffix = l[45]
        if main_suffix not in [" ","2"]:
            warn("main_suffix = %r"%(main_suffix,),UnrecognisedWarning)
        d["main_suffix"] = main_suffix
        
        association_type = l[47].strip()
        if association_type:
            d["association_type"] = association_type
            if association_type not in Schedule.association_type:
                warn("association_type = %r"%(association_type,),UnrecognisedWarning)

        stp_indicator = l[79]
        if stp_indicator not in Schedule.stp_indicator:
            warn("stp_indicator = %r"%(stp_indicator,),UnrecognisedWarning)
        d["stp_indicator"] = stp_indicator


    @linereader("TN")
    def read_TN(self):
        d = self.schedule
        l = self.line
        if "notes" not in d:
            notes = {}
            d["notes"] = notes
        else:
            notes = d["notes"]

        note_type = l[2].strip()
        if note_type not in notes:
            notes[note_type] = ""
        notes[note_type] = (notes[note_type] + "\n" + l[3:80]).strip()


    @linereader("LO")
    def read_LO(self):
        a = self.location
        l = self.line

        a["type"] = "origin"
        a["location"] = l[2:10].strip()
        
        scheduled_departure = time_hhmmx(l[10:15])
        if scheduled_departure is not None:
            a["scheduled_departure"] = scheduled_departure

        a["public_departure"] = time_hhmm(l[15:19])
        a["platform"] = l[19:22].strip()
        a["line"] = l[22:25].strip()

        engineering_allowance = timedelta_minh(l[25:27])
        if engineering_allowance is not None:
            a["engineering_allowance"] = engineering_allowance

        pathing_allowance = timedelta_minh(l[27:29])
        if pathing_allowance is not None:
            a["pathing_allowance"] = pathing_allowance

        activities = parse_activities(l[29:41])
        if "TB" not in activities:
            warn("TB is not in train activities", WeirdBehaviour)
        a["train_activity"] = activities

        performance_allowance = timedelta_minh(l[41:43])
        if performance_allowance is not None:
            a["performance_allowance"] = performance_allowance
        

    @linereader("LI")
    def read_LI(self):
        a = self.location
        l = self.line

        a["type"] = "intermediate"
        a["location"] = l[2:10].strip()
        a["scheduled_arrival"] = time_hhmmx(l[10:15])
        a["scheduled_departure"] = time_hhmmx(l[15:20])
        a["scheduled_pass"] = time_hhmmx(l[20:25])
        a["public_arrival"] = time_hhmm(l[25:29])
        a["public_departure"] = time_hhmm(l[29:33])
        a["platform"] = l[33:36].strip()
        a["line"] = l[36:39].strip()
        a["path"] = l[39:42].strip()
        a["train_activity"] = parse_activities(l[42:54])
        
        engineering_allowance = timedelta_minh(l[54:56])
        if engineering_allowance is not None:
            a["engineering_allowance"] = engineering_allowance

        pathing_allowance = timedelta_minh(l[56:58])
        if pathing_allowance is not None:
            a["pathing_allowance"] = pathing_allowance

        performance_allowance = timedelta_minh(l[58:60])
        if performance_allowance is not None:
            a["performance_allowance"] = performance_allowance
 

    @linereader("CR")
    def read_CR(self):
        d = self.location
        l = self.line

        d["type"] = "change"
        d["location"] = l[2:10].strip()

        category = l[10:12].strip()
        if category:
            d["category"] = category
            if category not in Schedule.category:
                warn("category = %r"%(category,),UnrecognisedWarning)

        identity = l[12:16].strip()
        if identity:
            d["identity"] = identity
    
        headcode = l[16:20].strip()
        if headcode:
            d["headcode"] = headcode

        service_code = l[21:29].strip()
        if service_code:
            d["service_code"] = service_code
        
        portion_id = l[29].strip()
        if portion_id:
            d["portion_id"] = portion_id

        power_type = l[30:33].strip()
        if power_type:
            d["power_type"] = power_type
            if power_type not in Schedule.power_type:
                warn("power_type = %r"%(power_type,),UnrecognisedWarning)

        timing_load = l[33:37].strip()
        if timing_load:
            if parse_timing_load(power_type, timing_load) is None:
                warn("timing_load = %r (with power_type = %r)", (timing_load, power_type), UnrecognisedWarning)
            d["timing_load"] = timing_load

        d["speed"] = int(l[37:40].strip() or 0)

        operating_chars = list(l[40:46].strip())
        d["operating_chars"] = operating_chars
        for c in operating_chars:
            if c not in Schedule.operating_chars:
                warn("operating_chars has %r"%(c,),UnrecognisedWarning)

        train_class = l[46].strip() or "B"
        d["train_class"] = train_class
        if train_class not in Schedule.train_class:
            warn("train_class = %r"%(train_class,),UnrecognisedWarning)  
        sleepers = l[47].strip()
        if sleepers:
            d["sleepers"] = sleepers
            if sleepers not in Schedule.sleepers:
                warn("sleepers = %r"%(sleepers,),UnrecognisedWarning)

        reservations = l[48].strip()
        if reservations:
            d["reservations"] = reservations
            if reservations not in Schedule.reservations:
                warn("reservations = %r"%(sleepers,),UnrecognisedWarning)

        connection_indicator = l[49].strip()
        if connection_indicator:
            d["connection_indicator"] = connection_indicator
            if connection_indicator not in Schedule.connection_indicator:
                warn("connection_indicator = %r"%(connection_indicator,),UnrecognisedWarning)

        catering = list(l[50:54].strip())
        d["catering"] = catering
        for c in catering:
            if c not in Schedule.catering:
                warn("catering has %r"%(c,),UnrecognisedWarning)
        
        service_branding = list(l[54:58].strip())
        d["service_branding"] = service_branding
        for c in service_branding:
            if c not in Schedule.service_branding:
                warn("service_branding has %r"%(c,),UnrecognisedWarning)

        uic_code = l[62:67].strip()
        if uic_code:
            d["uic_code"] = uic_code

        rsid = l[67:75].strip()
        if rsid:
            d["rsid"] = rsid


    @linereader("LT")
    def read_LT(self):
        a = self.location
        l = self.line

        a["type"] = "terminating"
        a["location"] = l[2:10].strip()
        a["scheduled_arrival"] = time_hhmmx(l[10:15])
        a["public_arrival"] = time_hhmm(l[15:19])
        a["platform"] = l[19:22].strip()
        a["path"] = l[22:25].strip()

        train_activity = parse_activities(l[25:37])
        if 'TF' not in train_activity:
            warn("TF is not in train activities", WeirdBehaviour)
        a["train_activity"] = train_activity


    @linereader("LN")
    def read_LN(self):
        d = self.location
        l = self.line
        if "notes" not in d:
            notes = {}
            d["notes"] = notes
        else:
            notes = d["notes"]

        note_type = l[2].strip()
        if note_type not in notes:
            notes[note_type] = ""
        notes[note_type] = (notes[note_type] + "\n" + l[3:80]).strip()


    @linereader("ZZ")
    def read_ZZ(self):
        # Trailer
        pass


    @linereader("EOF")
    def finish(self):
        self.end()


    def parse(self,filename):

        with open(filename,'r') as f:
            self.begin()

            self.iterator = iter(f)
            self.nextline()
            self.header = None

            self.read_HD()
            self.write_header()

            while self.record_type == "TI":
                self.tiploc = {}
                self.read_TI()
                self.write_tiploc()

            while self.record_type == "TA":
                self.tiploc = {}
                self.read_TA()
                self.write_tiploc()

            while self.record_type == "TD":
                self.tiploc = {}
                self.read_TD()
                self.write_tiploc()

            while self.record_type == "AA":
                self.association = {}
                self.read_AA()
                self.write_association

            while self.record_type == "BS":
                self.schedule = {}
                self.locations = []
                self.read_BS()
                if self.record_type == "BX":
                    self.read_BX()
                while self.record_type == "TN":
                    self.read_TN()
                while self.record_type == "LO":
                    self.location = {}
                    self.read_LO()
                    while self.record_type == "LN":
                        self.read_LN()
                    self.locations.append(self.location)
                while self.record_type == "CR" or self.record_type == "LI":
                    if self.record_type == "CR":
                        self.location = {}
                        self.read_CR()
                        self.locations.append(self.location)
                    self.location = {}
                    self.read_LI()
                    while self.record_type == "LN":
                        self.read_LN()
                    self.locations.append(self.location)
                while self.record_type == "LT":
                    self.location = {}
                    self.read_LT()
                    while self.record_type == "LN":
                        self.read_LN()
                    self.locations.append(self.location)
                self.schedule["locations"] = self.locations
                self.write_schedule()

            self.read_ZZ()
            self.finish()


    def write_header(self):
        "Stores self.header in the appropriate way"
        pass


    def write_schedule(self):
        "Stores self.schedule in the appropriate way"
        pass


    def write_tiploc(self):
        "Stores self.tiploc in the appropriate way"
        pass


    def write_association(self):
        "Stores self.association in the appropriate way"
        pass


    def begin(self):
        "Prepare for parsing run"
        pass


    def end(self):
        "Tidy up after parsing run"
        pass

