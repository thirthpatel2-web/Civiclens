// CivicLens - Civic GPS & Nearby Government Offices Locator

export const NEARBY_CIVIC_OFFICES = {
  bengaluru: [
    {
      id: 'blr_ward_150',
      type: 'Municipal Ward Office',
      name: 'BBMP Ward 150 (Bellandur) Office',
      icon: '🏛️',
      category: 'Municipal Administration',
      address: 'Near Outer Ring Road, Bellandur, Bengaluru 560103',
      phone: '080-22660000',
      distanceKm: 1.8,
      estTimeMins: 6,
      hours: '10:00 AM - 5:30 PM (Mon-Sat)',
      officer: 'Assistant Executive Engineer (AEE)',
      services: ['Pothole Complaints', 'Trade License', 'Birth/Death Certificate', 'Property Tax (Khata)']
    },
    {
      id: 'blr_police_hsr',
      type: 'Police Station',
      name: 'HSR Layout Police Station (Law & Order)',
      icon: '🚨',
      category: 'Law & Order',
      address: '27th Main Rd, Sector 1, HSR Layout, Bengaluru 560102',
      phone: '080-22943468',
      emergencyPhone: '112',
      distanceKm: 2.4,
      estTimeMins: 8,
      hours: '24 Hours Open',
      officer: 'Station House Officer (Inspector)',
      services: ['Zero FIR Registration', 'Lost Report / NCR', 'Cyber Crime Intimation', 'Senior Citizen Safety']
    },
    {
      id: 'blr_bescom_e4',
      type: 'Electricity Sub-Station',
      name: 'BESCOM E-4 Sub-Division Office',
      icon: '⚡',
      category: 'Power & Energy',
      address: '14th Main Rd, Sector 3, HSR Layout, Bengaluru 560102',
      phone: '1912',
      distanceKm: 2.1,
      estTimeMins: 7,
      hours: '9:30 AM - 5:00 PM',
      officer: 'Assistant Executive Engineer (Elec)',
      services: ['Power Outage Escalation', 'New Meter Connection', 'Voltage Fluctuation Claims']
    },
    {
      id: 'blr_bwssb_east',
      type: 'Water & Sewerage Office',
      name: 'BWSSB Service Station (Indiranagar / East)',
      icon: '💧',
      category: 'Water Utility',
      address: '100ft Road, Near BSNL Tower, Indiranagar, Bengaluru 560038',
      phone: '1916',
      distanceKm: 3.5,
      estTimeMins: 12,
      hours: '10:00 AM - 5:00 PM',
      officer: 'Assistant Engineer (Water Supply)',
      services: ['Pipeline Fracture Repair', 'Sewage Blockage Jetting', 'Cauvery Water Connection']
    },
    {
      id: 'blr_consumer_court',
      type: 'Consumer Court',
      name: 'Bangalore Urban District Consumer Forum',
      icon: '⚖️',
      category: 'Judiciary & Rights',
      address: 'KHB Complex, Cauvery Bhavan, KG Road, Bengaluru 560009',
      phone: '080-22211145',
      distanceKm: 6.8,
      estTimeMins: 22,
      hours: '10:30 AM - 4:30 PM (Mon-Fri)',
      officer: 'Registrar, DCDRC',
      services: ['E-Daakhil Physical Counter', 'Consumer Grievance Hearings', 'Execution Petitions']
    }
  ],

  delhi: [
    {
      id: 'del_mcd_office',
      type: 'Municipal Ward Office',
      name: 'MCD Zonal Office (City-SP Zone)',
      icon: '🏛️',
      category: 'Municipal Administration',
      address: 'Nigambodh Ghat Road, Kashmere Gate, Delhi 110006',
      phone: '155304',
      distanceKm: 2.2,
      estTimeMins: 8,
      hours: '9:30 AM - 5:30 PM',
      officer: 'Zonal Deputy Commissioner',
      services: ['Sanitation Grievances', 'Building Permissions', 'Encroachment Removal']
    },
    {
      id: 'del_police_stn',
      type: 'Police Station',
      name: 'Connaught Place Police Station',
      icon: '🚨',
      category: 'Law & Order',
      address: 'Shaheed Bhagat Singh Marg, CP, New Delhi 110001',
      phone: '011-23340000',
      distanceKm: 3.1,
      estTimeMins: 10,
      hours: '24 Hours Open',
      officer: 'SHO Connaught Place',
      services: ['Zero FIR', 'Women Safety Helpdesk', 'Cyber Complaints']
    }
  ]
};

export const getNearbyCivicOffices = (cityId = 'bengaluru') => {
  return NEARBY_CIVIC_OFFICES[cityId] || NEARBY_CIVIC_OFFICES['bengaluru'];
};
